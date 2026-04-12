"""
HTTP-facing sync ingest (Issue #1 shell, Issue #2 merge).

Merge rules live in `merge_service` / `merge_policy`; this module maps results to API models.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.sync import SyncPushRequest, SyncPushResponse
from app.services.merge_service import MergeService


async def process_sync_push(
    session: AsyncSession,
    body: SyncPushRequest,
    header_gateway_id: UUID,
    header_batch_id: UUID,
) -> SyncPushResponse:
    result = await MergeService.apply_batch(session, body, header_gateway_id, header_batch_id)
    return SyncPushResponse(
        idempotent_replay=result.idempotent_replay,
        record_count=result.record_count,
        applied_count=result.applied_count,
        rejected=[],
        sync_log_status=result.sync_log_status,
    )
