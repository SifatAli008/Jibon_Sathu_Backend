from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from packaging.version import Version

from app.config import get_settings
from app.grpc_service.ingest import _client_version_ok
from app.main import app
from app.services.triage_logic import compute_priority_score


def test_triage_priority_sos_highest() -> None:
    assert compute_priority_score("sos", "open", {}) >= 99.0


def test_triage_priority_road_damaged() -> None:
    s = compute_priority_score("road", "damaged", {})
    assert s >= 70.0


def test_grpc_client_version_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRPC_MIN_CLIENT_VERSION", "1.0.0")
    get_settings.cache_clear()
    try:
        assert _client_version_ok((("x-client-version", "1.0.0"),))
        assert not _client_version_ok((("x-client-version", "0.0.1"),))
    finally:
        monkeypatch.delenv("GRPC_MIN_CLIENT_VERSION", raising=False)
        get_settings.cache_clear()


def test_version_compare_packaging() -> None:
    assert Version("2.0.0") >= Version("1.0.0")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analytics_requires_admin(ac: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_ADMIN_KEY", "dash-secret")
    get_settings.cache_clear()
    try:
        r = await ac.get("/v1/analytics/map-layers")
        assert r.status_code == 401
        ok = await ac.get("/v1/analytics/map-layers", headers={"X-Dashboard-Admin-Key": "dash-secret"})
        assert ok.status_code == 200
        assert ok.json().get("type") == "FeatureCollection"
    finally:
        monkeypatch.delenv("DASHBOARD_ADMIN_KEY", raising=False)
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_push_triggers_triage_eager(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    get_settings.cache_clear()
    import importlib

    import app.worker as worker_mod

    importlib.reload(worker_mod)
    try:
        gid = uuid.uuid4()
        bid = uuid.uuid4()
        rid = uuid.uuid4()
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        r = await ac.post(
            "/v1/sync/push",
            json={
                "gateway_id": str(gid),
                "batch_id": str(bid),
                "reports": [
                    {
                        "id": str(rid),
                        "kind": "road",
                        "segment_key": f"TR-{uuid.uuid4()}",
                        "status": "ok",
                        "payload": {"lat": 23.7, "lon": 90.4},
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            },
            headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid)},
        )
        assert r.status_code == 200, r.text

        from sqlalchemy import select

        from app.db import get_session_factory
        from app.models import Report

        factory = get_session_factory()
        async with factory() as session:
            row = await session.scalar(select(Report).where(Report.id == rid))
            assert row is not None
            assert row.triage_status == "completed"
            assert row.priority_score is not None
    finally:
        monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        get_settings.cache_clear()


def test_enqueue_called_on_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    get_settings.cache_clear()
    try:
        with patch("app.worker.triage_reports_task.delay") as delay_mock:
            from app.services.triage_enqueue import maybe_enqueue_triage

            u = uuid.uuid4()
            maybe_enqueue_triage((u,))
            delay_mock.assert_called_once_with([str(u)])
    finally:
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
        get_settings.cache_clear()


@pytest.fixture
async def ac() -> AsyncClient:
    from app.db import dispose_db_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_db_engine()
