from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.config import get_settings
from app.db import get_session_factory
from app.deps.gateway_auth import hash_gateway_secret
from app.main import app
from app.models import Gateway, Report
from app.schemas.sync import ReportItem, ReportKind
from app.services.merge_policy import MutableMergeAction, decide_road_like_merge, incoming_is_tombstone


@pytest.fixture
async def ac() -> AsyncClient:
    from app.db import dispose_db_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_db_engine()


def test_tombstone_blocks_resurrection_even_if_incoming_is_newer_wall_clock() -> None:
    t_live = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
    t_stale_incoming = datetime(2026, 4, 12, 12, 0, 0, tzinfo=UTC)
    canonical_id = uuid.uuid4()
    incoming_id = uuid.uuid4()
    g = uuid.uuid4()
    inc = ReportItem(
        id=incoming_id,
        kind=ReportKind.road,
        segment_key="SEG",
        status="alive",
        payload={},
        created_at=t_stale_incoming,
        updated_at=t_stale_incoming,
    )
    snap = {
        "id": canonical_id,
        "updated_at": t_live,
        "source_gateway_id": g,
        "is_tombstone": True,
        "server_sequence_id": 10,
    }
    d = decide_road_like_merge(incoming=inc, incoming_gateway_id=g, canonical_existing=snap)
    assert d.action == MutableMergeAction.noop
    assert incoming_is_tombstone(inc) is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_push_delete_creates_tombstone(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORTS_DEV_KEY", "dev-test-key")
    get_settings.cache_clear()
    try:
        seg = f"TOMB-{uuid.uuid4()}"
        gid = uuid.uuid4()
        bid = uuid.uuid4()
        rid = uuid.uuid4()
        t0 = (datetime.now(UTC) - timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        t1 = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        assert (
            await ac.post(
                "/sync/push",
                json={
                    "gateway_id": str(gid),
                    "batch_id": str(bid),
                    "reports": [
                        {
                            "id": str(rid),
                            "kind": "road",
                            "segment_key": seg,
                            "status": "ok",
                            "payload": {"n": 1},
                            "created_at": t0,
                            "updated_at": t0,
                        }
                    ],
                },
                headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
            )
        ).status_code == 200

        bid2 = uuid.uuid4()
        assert (
            await ac.post(
                "/sync/push",
                json={
                    "gateway_id": str(gid),
                    "batch_id": str(bid2),
                    "reports": [
                        {
                            "id": str(uuid.uuid4()),
                            "kind": "road",
                            "segment_key": seg,
                            "status": "deleted",
                            "payload": {},
                            "created_at": t0,
                            "updated_at": t1,
                            "deleted_at": t1,
                        }
                    ],
                },
                headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid2)},
            )
        ).status_code == 200

        lr = await ac.get("/reports", headers={"X-Dev-Reports-Key": "dev-test-key"})
        row = next(x for x in lr.json() if x.get("segment_key") == seg)
        # Dev endpoint may not expose is_tombstone; validate via pull instead:
        pr = await ac.get("/sync/pull", headers={"X-Gateway-Id": str(gid)}, params={"since_sequence_id": 0})
        assert pr.status_code == 200
        items = pr.json()["items"]
        hit = next(x for x in items if x.get("segment_key") == seg)
        assert hit["is_tombstone"] is True
        assert hit.get("deleted_at") is not None
    finally:
        monkeypatch.delenv("REPORTS_DEV_KEY", raising=False)
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stale_live_push_after_tombstone_is_noop(ac: AsyncClient) -> None:
    seg = f"ZOMB-{uuid.uuid4()}"
    gid = uuid.uuid4()
    t_base = datetime.now(UTC) - timedelta(hours=5)
    t_del = t_base + timedelta(hours=1)
    t_stale_live = t_base + timedelta(minutes=30)

    b1 = uuid.uuid4()
    rid = uuid.uuid4()
    assert (
        await ac.post(
            "/sync/push",
            json={
                "gateway_id": str(gid),
                "batch_id": str(b1),
                "reports": [
                    {
                        "id": str(rid),
                        "kind": "road",
                        "segment_key": seg,
                        "status": "ok",
                        "payload": {"n": 1},
                        "created_at": t_base.isoformat().replace("+00:00", "Z"),
                        "updated_at": t_base.isoformat().replace("+00:00", "Z"),
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(b1)},
        )
    ).status_code == 200

    b2 = uuid.uuid4()
    assert (
        await ac.post(
            "/sync/push",
            json={
                "gateway_id": str(gid),
                "batch_id": str(b2),
                "reports": [
                    {
                        "id": str(uuid.uuid4()),
                        "kind": "road",
                        "segment_key": seg,
                        "status": "deleted",
                        "payload": {},
                        "created_at": t_base.isoformat().replace("+00:00", "Z"),
                        "updated_at": t_del.isoformat().replace("+00:00", "Z"),
                        "deleted_at": t_del.isoformat().replace("+00:00", "Z"),
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(b2)},
        )
    ).status_code == 200

    b3 = uuid.uuid4()
    r3 = await ac.post(
        "/sync/push",
        json={
            "gateway_id": str(gid),
            "batch_id": str(b3),
            "reports": [
                {
                    "id": str(uuid.uuid4()),
                    "kind": "road",
                    "segment_key": seg,
                    "status": "resurrected",
                    "payload": {"oops": True},
                    "created_at": t_base.isoformat().replace("+00:00", "Z"),
                    "updated_at": t_stale_live.isoformat().replace("+00:00", "Z"),
                }
            ],
        },
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(b3)},
    )
    assert r3.status_code == 200
    assert r3.json()["applied_count"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pull_delta_respects_since_sequence_id(ac: AsyncClient) -> None:
    gid = uuid.uuid4()
    seg = f"PULL-{uuid.uuid4()}"
    t = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    b = uuid.uuid4()
    rid = uuid.uuid4()
    assert (
        await ac.post(
            "/sync/push",
            json={
                "gateway_id": str(gid),
                "batch_id": str(b),
                "reports": [
                    {
                        "id": str(rid),
                        "kind": "road",
                        "segment_key": seg,
                        "status": "ok",
                        "payload": {},
                        "created_at": t,
                        "updated_at": t,
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(b)},
        )
    ).status_code == 200

    r0 = await ac.get("/sync/pull", headers={"X-Gateway-Id": str(gid)}, params={"since_sequence_id": 0})
    assert r0.status_code == 200
    j0 = r0.json()
    assert j0["has_more"] is False
    assert j0["max_sequence_id"] > 0
    mx = j0["max_sequence_id"]

    r1 = await ac.get("/sync/pull", headers={"X-Gateway-Id": str(gid)}, params={"since_sequence_id": mx})
    assert r1.status_code == 200
    assert r1.json()["items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sequence_monotonic_across_concurrent_pushes(ac: AsyncClient) -> None:
    run = uuid.uuid4().hex[:10]

    async def one_push(i: int) -> None:
        gid = uuid.uuid4()
        bid = uuid.uuid4()
        t = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        r = await ac.post(
            "/sync/push",
            json={
                "gateway_id": str(gid),
                "batch_id": str(bid),
                "reports": [
                    {
                        "id": str(uuid.uuid4()),
                        "kind": "road",
                        "segment_key": f"CONC-{run}-{i}",
                        "status": "ok",
                        "payload": {},
                        "created_at": t,
                        "updated_at": t,
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
        )
        assert r.status_code == 200

    await asyncio.gather(*(one_push(i) for i in range(8)))

    factory = get_session_factory()
    async with factory() as session:
        rows = list(
            await session.scalars(
                select(Report).where(Report.segment_key.startswith(f"CONC-{run}-"))
            )
        )
        assert len(rows) == 8
        seqs = [r.server_sequence_id for r in rows]
        assert len(set(seqs)) == 8


@pytest.mark.integration
@pytest.mark.asyncio
async def test_push_payload_too_large_413(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_SYNC_BATCH_ITEMS", "2")
    get_settings.cache_clear()
    try:
        gid = uuid.uuid4()
        bid = uuid.uuid4()
        t = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        items = [
            {
                "id": str(uuid.uuid4()),
                "kind": "road",
                "segment_key": f"BIG-{i}",
                "status": "ok",
                "payload": {},
                "created_at": t,
                "updated_at": t,
            }
            for i in range(3)
        ]
        r = await ac.post(
            "/sync/push",
            json={"gateway_id": str(gid), "batch_id": str(bid), "reports": items},
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
        )
        assert r.status_code == 413
    finally:
        monkeypatch.delenv("MAX_SYNC_BATCH_ITEMS", raising=False)
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gateway_auth_missing_headers_401(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_GATEWAY_AUTH", "true")
    get_settings.cache_clear()
    try:
        r = await ac.get("/sync/pull", headers={"X-Gateway-Id": str(uuid.uuid4())})
        assert r.status_code == 401
    finally:
        monkeypatch.delenv("REQUIRE_GATEWAY_AUTH", raising=False)
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gateway_auth_revoked_403(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_GATEWAY_AUTH", "true")
    get_settings.cache_clear()
    gid = uuid.uuid4()
    secret = "super-secret"
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            session.add(
                Gateway(
                    id=gid,
                    name="t",
                    auth_secret_hash=hash_gateway_secret(secret),
                    revoked_at=datetime.now(UTC),
                )
            )
    try:
        r = await ac.get(
            "/sync/pull",
            headers={"X-Gateway-Id": str(gid), "Authorization": f"Bearer {secret}"},
        )
        assert r.status_code == 403
    finally:
        monkeypatch.delenv("REQUIRE_GATEWAY_AUTH", raising=False)
        get_settings.cache_clear()
        async with factory() as session:
            async with session.begin():
                await session.execute(text("DELETE FROM gateways WHERE id = :id"), {"id": gid})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gateway_auth_ok_200(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_GATEWAY_AUTH", "true")
    get_settings.cache_clear()
    gid = uuid.uuid4()
    secret = "super-secret-2"
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            session.add(
                Gateway(
                    id=gid,
                    name="t",
                    auth_secret_hash=hash_gateway_secret(secret),
                    revoked_at=None,
                )
            )
    try:
        r = await ac.get(
            "/sync/pull",
            headers={"X-Gateway-Id": str(gid), "Authorization": f"Bearer {secret}"},
        )
        assert r.status_code == 200
    finally:
        monkeypatch.delenv("REQUIRE_GATEWAY_AUTH", raising=False)
        get_settings.cache_clear()
        async with factory() as session:
            async with session.begin():
                await session.execute(text("DELETE FROM gateways WHERE id = :id"), {"id": gid})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conflicts_admin_endpoint(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNC_ADMIN_KEY", "adm")
    get_settings.cache_clear()
    try:
        r = await ac.get("/sync/conflicts", headers={"X-Sync-Admin-Key": "adm"})
        assert r.status_code == 200
        assert "items" in r.json()
    finally:
        monkeypatch.delenv("SYNC_ADMIN_KEY", raising=False)
        get_settings.cache_clear()
