"""REST vs gRPC ingest parity — same MergeService path (Issue #12)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db import get_session_factory
from app.grpc_gen import sync_pb2
from app.grpc_service.ingest import SyncIngestServicer
from app.main import app
from app.models import Report


def _report_compare_dict(row: Report) -> dict:
    return {
        "kind": row.kind,
        "segment_key": row.segment_key,
        "status": row.status,
        "payload": dict(row.payload or {}),
        "source_gateway_id": row.source_gateway_id,
        "is_tombstone": row.is_tombstone,
        "triage_status": row.triage_status,
        "priority_score": row.priority_score,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@pytest.fixture
async def ac() -> AsyncClient:
    from app.db import dispose_db_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_db_engine()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_and_grpc_produce_matching_report_row(ac: AsyncClient) -> None:
    gid = uuid.uuid4()
    bid_rest = uuid.uuid4()
    bid_grpc = uuid.uuid4()
    rid = uuid.uuid4()
    seg = f"GRPC-PAR-{uuid.uuid4()}"
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {"notes": "parity", "lat": 23.71, "lon": 90.41}
    body = {
        "gateway_id": str(gid),
        "batch_id": str(bid_rest),
        "gateway_name": "parity-gw",
        "reports": [
            {
                "id": str(rid),
                "kind": "road",
                "segment_key": seg,
                "status": "damaged",
                "payload": payload,
                "created_at": now,
                "updated_at": now,
            }
        ],
    }
    r = await ac.post(
        "/v1/sync/push",
        json=body,
        headers={"X-Gateway-Id": str(gid), "X-Sync-Batch-Id": str(bid_rest)},
    )
    assert r.status_code == 200, r.text

    factory = get_session_factory()
    async with factory() as session:
        row_rest = await session.scalar(select(Report).where(Report.segment_key == seg))
        assert row_rest is not None
        snap_rest = _report_compare_dict(row_rest)
        await session.execute(delete(Report).where(Report.segment_key == seg))
        await session.commit()

    req = sync_pb2.PushBatchRequest()
    req.gateway_id = str(gid)
    req.batch_id = str(bid_grpc)
    req.gateway_name = "parity-gw"
    ri = req.reports.add()
    ri.id = str(rid)
    ri.kind = "road"
    ri.segment_key = seg
    ri.status = "damaged"
    ri.payload_json = json.dumps(payload)
    ri.created_at_rfc3339 = now
    ri.updated_at_rfc3339 = now

    ctx = MagicMock()
    ctx.invocation_metadata.return_value = (("x-client-version", "1.0.0"),)
    ctx.abort = AsyncMock()

    servicer = SyncIngestServicer()
    out = await servicer.PushBatch(req, ctx)
    assert out.record_count == 1
    assert out.applied_count == 1
    assert out.idempotent_replay is False
    ctx.abort.assert_not_called()

    async with factory() as session:
        row_grpc = await session.scalar(select(Report).where(Report.segment_key == seg))
        assert row_grpc is not None
        snap_grpc = _report_compare_dict(row_grpc)

    assert snap_rest == snap_grpc
