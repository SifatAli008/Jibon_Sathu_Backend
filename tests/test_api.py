from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app


@pytest.fixture
async def ac() -> AsyncClient:
    from app.db import dispose_db_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_db_engine()


@pytest.mark.asyncio
async def test_health_returns_json(ac: AsyncClient) -> None:
    r = await ac.get("/health")
    assert r.status_code in (200, 503)
    data = r.json()
    assert "status" in data and "db" in data


@pytest.mark.asyncio
async def test_reports_dev_endpoint_hidden_without_key(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPORTS_DEV_KEY", raising=False)
    get_settings.cache_clear()
    r = await ac.get("/reports")
    assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_push_minimal_batch(ac: AsyncClient) -> None:
    gid = uuid.uuid4()
    bid = uuid.uuid4()
    rid = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "gateway_id": str(gid),
        "batch_id": str(bid),
        "gateway_name": "test-gateway",
        "reports": [
            {
                "id": str(rid),
                "kind": "road",
                "segment_key": "BD-DHK-12-450",
                "status": "damaged",
                "payload": {"notes": "crack"},
                "created_at": now,
                "updated_at": now,
            }
        ],
    }
    r = await ac.post(
        "/v1/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["record_count"] == 1
    assert out["applied_count"] == 1
    assert out["idempotent_replay"] is False

    r2 = await ac.post(
        "/v1/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
    )
    assert r2.status_code == 200
    out2 = r2.json()
    assert out2["idempotent_replay"] is True


@pytest.mark.asyncio
async def test_push_header_body_mismatch(ac: AsyncClient) -> None:
    gid = uuid.uuid4()
    other = uuid.uuid4()
    bid = uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "gateway_id": str(gid),
        "batch_id": str(bid),
        "reports": [],
    }
    r = await ac.post(
        "/v1/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(other), "X-Sync-Batch-Id": str(bid)},
    )
    assert r.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_push_strict_clock_skew_fails_whole_batch(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPORTS_DEV_KEY", raising=False)
    get_settings.cache_clear()
    gid = uuid.uuid4()
    bid = uuid.uuid4()
    now = datetime.now(UTC)
    far = (now + timedelta(days=400)).isoformat().replace("+00:00", "Z")
    ok_iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "gateway_id": str(gid),
        "batch_id": str(bid),
        "reports": [
            {
                "id": str(uuid.uuid4()),
                "kind": "sos",
                "status": "open",
                "payload": {},
                "created_at": ok_iso,
                "updated_at": ok_iso,
            },
            {
                "id": str(uuid.uuid4()),
                "kind": "road",
                "status": "ok",
                "payload": {},
                "created_at": far,
                "updated_at": far,
            },
        ],
    }
    r = await ac.post(
        "/v1/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
    )
    assert r.status_code == 422, r.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_segment_conflict_two_gateways_latest_wins(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPORTS_DEV_KEY", "dev-test-key")
    get_settings.cache_clear()
    try:
        seg = f"SEG-{uuid.uuid4()}"
        t1 = (datetime.now(UTC) - timedelta(hours=3)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        t2 = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        gid1 = uuid.uuid4()
        bid1 = uuid.uuid4()
        rid1 = uuid.uuid4()
        r1 = await ac.post(
            "/v1/sync/push",
            json={
                "gateway_id": str(gid1),
                "batch_id": str(bid1),
                "reports": [
                    {
                        "id": str(rid1),
                        "kind": "road",
                        "segment_key": seg,
                        "status": "ok",
                        "payload": {"who": "gw1"},
                        "created_at": t1,
                        "updated_at": t1,
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid1), "X-Sync-Batch-Id": str(bid1)},
        )
        assert r1.status_code == 200, r1.text

        gid2 = uuid.uuid4()
        bid2 = uuid.uuid4()
        rid2 = uuid.uuid4()
        r2 = await ac.post(
            "/v1/sync/push",
            json={
                "gateway_id": str(gid2),
                "batch_id": str(bid2),
                "reports": [
                    {
                        "id": str(rid2),
                        "kind": "road",
                        "segment_key": seg,
                        "status": "blocked",
                        "payload": {"who": "gw2"},
                        "created_at": t2,
                        "updated_at": t2,
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid2), "X-Sync-Batch-Id": str(bid2)},
        )
        assert r2.status_code == 200, r2.text

        lr = await ac.get("/reports", headers={"X-Dev-Reports-Key": "dev-test-key"})
        assert lr.status_code == 200, lr.text
        rows = lr.json()
        match = [x for x in rows if x.get("segment_key") == seg]
        assert len(match) == 1
        assert match[0]["status"] == "blocked"
        assert match[0]["id"] == str(rid1)
        assert match[0]["payload"]["who"] == "gw2"
    finally:
        monkeypatch.delenv("REPORTS_DEV_KEY", raising=False)
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sos_first_write_immutable(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORTS_DEV_KEY", "dev-test-key")
    get_settings.cache_clear()
    try:
        sid = uuid.uuid4()
        gid = uuid.uuid4()
        t = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        b1 = uuid.uuid4()
        r1 = await ac.post(
            "/v1/sync/push",
            json={
                "gateway_id": str(gid),
                "batch_id": str(b1),
                "reports": [
                    {
                        "id": str(sid),
                        "kind": "sos",
                        "status": "open",
                        "payload": {"text": "first"},
                        "created_at": t,
                        "updated_at": t,
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(b1)},
        )
        assert r1.status_code == 200

        b2 = uuid.uuid4()
        r2 = await ac.post(
            "/v1/sync/push",
            json={
                "gateway_id": str(gid),
                "batch_id": str(b2),
                "reports": [
                    {
                        "id": str(sid),
                        "kind": "sos",
                        "status": "closed",
                        "payload": {"text": "second"},
                        "created_at": t,
                        "updated_at": t,
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(b2)},
        )
        assert r2.status_code == 200
        assert r2.json()["applied_count"] == 0

        lr = await ac.get("/reports", headers={"X-Dev-Reports-Key": "dev-test-key"})
        sos = next(x for x in lr.json() if x["id"] == str(sid))
        assert sos["payload"]["text"] == "first"
    finally:
        monkeypatch.delenv("REPORTS_DEV_KEY", raising=False)
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_simulated_fault_rollbacks_entire_batch(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import merge_service

    monkeypatch.setenv("REPORTS_DEV_KEY", "dev-test-key")
    get_settings.cache_clear()
    merge_service.set_merge_fault_after_touches(2)
    try:
        prefix = f"FAULT-{uuid.uuid4()}"
        gid = uuid.uuid4()
        bid = uuid.uuid4()
        t = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        body = {
            "gateway_id": str(gid),
            "batch_id": str(bid),
            "reports": [
                {
                    "id": str(uuid.uuid4()),
                    "kind": "road",
                    "segment_key": f"{prefix}-a",
                    "status": "a",
                    "payload": {},
                    "created_at": t,
                    "updated_at": t,
                },
                {
                    "id": str(uuid.uuid4()),
                    "kind": "road",
                    "segment_key": f"{prefix}-b",
                    "status": "b",
                    "payload": {},
                    "created_at": t,
                    "updated_at": t,
                },
                {
                    "id": str(uuid.uuid4()),
                    "kind": "road",
                    "segment_key": f"{prefix}-c",
                    "status": "c",
                    "payload": {},
                    "created_at": t,
                    "updated_at": t,
                },
            ],
        }
        r = await ac.post(
            "/v1/sync/push",
            json=body,
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
        )
        assert r.status_code == 500, r.text

        lr = await ac.get("/reports", headers={"X-Dev-Reports-Key": "dev-test-key"})
        assert lr.status_code == 200
        rows = [x for x in lr.json() if prefix in (x.get("segment_key") or "")]
        assert rows == []
    finally:
        merge_service.set_merge_fault_after_touches(None)
        monkeypatch.delenv("REPORTS_DEV_KEY", raising=False)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_legacy_unversioned_sync_route_not_found(ac: AsyncClient) -> None:
    """Issue #10: unversioned /sync/* must not match (contract frozen under /v1)."""
    r = await ac.post("/sync/push", json={"gateway_id": str(uuid.uuid4()), "batch_id": str(uuid.uuid4()), "reports": []})
    assert r.status_code == 404
