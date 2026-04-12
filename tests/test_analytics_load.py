"""Optional load-style check for analytics (Issue #13)."""

from __future__ import annotations

import os
import time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from app.config import get_settings
from app.main import app


@pytest.fixture
async def ac() -> AsyncClient:
    from app.db import dispose_db_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_db_engine()


@pytest.mark.load
@pytest.mark.integration
@pytest.mark.asyncio
async def test_map_layers_response_time_with_many_reports(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.environ.get("RUN_ANALYTICS_LOAD_TEST") != "1":
        pytest.skip("Set RUN_ANALYTICS_LOAD_TEST=1 to run this check")

    monkeypatch.setenv("DASHBOARD_ADMIN_KEY", "load-test-key")
    get_settings.cache_clear()
    try:
        url = get_settings().sync_database_url
        engine = create_engine(url, pool_pre_ping=True)
        segment = "bulk-load-test"
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO reports (
                      id, kind, payload, segment_key, status, created_at, updated_at,
                      server_sequence_id, is_tombstone, triage_status
                    )
                    SELECT gen_random_uuid(), 'road',
                      '{"lat": 23.7, "lon": 90.4}'::jsonb,
                      :seg, 'ok', now(), now(),
                      b.base + g.g, false, 'pending'
                    FROM (
                      SELECT COALESCE(MAX(server_sequence_id), 0) AS base FROM reports
                    ) AS b,
                    generate_series(1, 10000) AS g(g)
                    """
                ),
                {"seg": segment},
            )
            conn.commit()
        engine.dispose()

        t0 = time.perf_counter()
        r = await ac.get(
            "/v1/analytics/map-layers",
            headers={"X-Dashboard-Admin-Key": "load-test-key"},
        )
        elapsed = time.perf_counter() - t0
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("type") == "FeatureCollection"
        # Budget for shared CI runners; tune locally toward <100ms if needed
        assert elapsed < 0.5
    finally:
        url = get_settings().sync_database_url
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM reports WHERE segment_key = :seg"), {"seg": segment})
            conn.commit()
        engine.dispose()
        monkeypatch.delenv("DASHBOARD_ADMIN_KEY", raising=False)
        get_settings.cache_clear()
