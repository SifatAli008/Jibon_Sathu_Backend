"""gRPC SyncIngest servicer — delegates to MergeService (Issue #12)."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import grpc
from grpc.aio import ServicerContext
from packaging.version import InvalidVersion, Version

from app.config import get_settings
from app.db import get_session_factory
from app.grpc_gen import sync_pb2, sync_pb2_grpc
from app.schemas.sync import ReportItem, ReportKind, SyncPushRequest
from app.services.merge_service import MergeService
from app.services.triage_enqueue import maybe_enqueue_triage


def _parse_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _pb_to_request(pb: sync_pb2.PushBatchRequest) -> SyncPushRequest:
    reports: list[ReportItem] = []
    for r in pb.reports:
        payload = json.loads(r.payload_json or "{}")
        deleted = None
        da = getattr(r, "deleted_at_rfc3339", "") or ""
        if da:
            deleted = _parse_dt(da)
        reports.append(
            ReportItem(
                id=UUID(r.id),
                kind=ReportKind(r.kind),
                segment_key=r.segment_key or None,
                status=r.status or "",
                payload=payload,
                created_at=_parse_dt(r.created_at_rfc3339),
                updated_at=_parse_dt(r.updated_at_rfc3339),
                deleted_at=deleted,
                is_tombstone=None,
            )
        )
    gw = getattr(pb, "gateway_name", "") or ""
    return SyncPushRequest(
        gateway_id=UUID(pb.gateway_id),
        batch_id=UUID(pb.batch_id),
        gateway_name=gw or None,
        reports=reports,
    )


def _client_version_ok(metadata: tuple[tuple[str, str], ...]) -> bool:
    settings = get_settings()
    md = {k.lower(): v for k, v in metadata}
    raw = md.get("x-client-version") or md.get("x-gateway-version") or ""
    try:
        return Version(raw) >= Version(settings.grpc_min_client_version)
    except InvalidVersion:
        return False


class SyncIngestServicer(sync_pb2_grpc.SyncIngestServicer):
    async def PushBatch(
        self,
        request: sync_pb2.PushBatchRequest,
        context: ServicerContext,
    ) -> sync_pb2.PushBatchResponse:
        if not _client_version_ok(tuple(context.invocation_metadata())):
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"x-client-version must be >= {get_settings().grpc_min_client_version}",
            )

        body = _pb_to_request(request)
        factory = get_session_factory()
        async with factory() as session:
            async with session.begin():
                result = await MergeService.apply_batch(
                    session, body, body.gateway_id, body.batch_id
                )
        maybe_enqueue_triage(result.triage_report_ids)
        return sync_pb2.PushBatchResponse(
            idempotent_replay=result.idempotent_replay,
            record_count=result.record_count,
            applied_count=result.applied_count,
            sync_log_status=result.sync_log_status,
        )
