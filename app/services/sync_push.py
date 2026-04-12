"""
Batch sync ingest (Issue #1): validate timestamps, upsert reports by id, write SyncLogs.

Issue #2 replaces naive upsert with merge policy; keep orchestration here and SQL localized.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Gateway, Report, SyncLog
from app.schemas.sync import ReportItem, SyncPushRequest, SyncPushResponse


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _validate_timestamps(item: ReportItem, now: datetime, max_future: timedelta) -> str | None:
    limit = now + max_future
    if item.created_at > limit or item.updated_at > limit:
        return "created_at/updated_at too far in the future relative to server clock"
    return None


async def process_sync_push(
    session: AsyncSession,
    body: SyncPushRequest,
    header_gateway_id: UUID,
    header_batch_id: UUID,
) -> SyncPushResponse:
    if body.gateway_id != header_gateway_id:
        raise ValueError("gateway_id must match X-Gateway-Id header")
    if body.batch_id != header_batch_id:
        raise ValueError("batch_id must match X-Sync-Batch-Id header")

    settings = get_settings()
    max_future = timedelta(seconds=settings.max_future_skew_seconds)
    now = _utcnow()

    rejected: list[dict[str, Any]] = []
    clean: list[ReportItem] = []
    for r in body.reports:
        err = _validate_timestamps(r, now, max_future)
        if err:
            rejected.append({"id": str(r.id), "reason": err})
        else:
            clean.append(r)

    existing = await session.scalar(
        select(SyncLog).where(
            SyncLog.gateway_id == body.gateway_id,
            SyncLog.batch_id == body.batch_id,
        )
    )
    if existing is not None:
        return SyncPushResponse(
            idempotent_replay=True,
            record_count=existing.record_count,
            applied_count=existing.applied_count,
            rejected=[],
            sync_log_status=existing.status,
        )

    gateway_name = body.gateway_name or f"gateway-{str(body.gateway_id)[:8]}"
    await session.execute(
        pg_insert(Gateway)
        .values(
            id=body.gateway_id,
            name=gateway_name,
            last_seen_at=now,
        )
        .on_conflict_do_update(
            index_elements=[Gateway.id],
            set_={"last_seen_at": now, "name": gateway_name},
        )
    )

    applied = 0
    for r in clean:
        await session.execute(
            pg_insert(Report)
            .values(
                id=r.id,
                kind=r.kind.value,
                segment_key=r.segment_key,
                status=r.status,
                payload=r.payload,
                created_at=r.created_at,
                updated_at=r.updated_at,
                source_gateway_id=body.gateway_id,
                deleted_at=r.deleted_at,
            )
            .on_conflict_do_update(
                index_elements=[Report.id],
                set_={
                    "kind": r.kind.value,
                    "segment_key": r.segment_key,
                    "status": r.status,
                    "payload": r.payload,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "source_gateway_id": body.gateway_id,
                    "deleted_at": r.deleted_at,
                },
            )
        )
        applied += 1

    record_count = len(body.reports)
    sync_status = "partial" if rejected else "applied"
    session.add(
        SyncLog(
            gateway_id=body.gateway_id,
            batch_id=body.batch_id,
            record_count=record_count,
            applied_count=applied,
            status=sync_status,
            error_detail=("Some items rejected for clock skew" if rejected else None),
        )
    )

    return SyncPushResponse(
        idempotent_replay=False,
        record_count=record_count,
        applied_count=applied,
        rejected=rejected,
        sync_log_status=sync_status,
    )
