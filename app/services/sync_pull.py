"""Downward sync (`GET /v1/sync/pull`) — Issue #6."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelArtifact, Report
from app.schemas.sync import LatestModelVersionMeta, SyncPullReportItem, SyncPullResponse


async def build_sync_pull_response(
    session: AsyncSession,
    *,
    since_sequence_id: int,
    limit: int,
) -> SyncPullResponse:
    stmt = (
        select(Report)
        .where(Report.server_sequence_id > since_sequence_id)
        .order_by(Report.server_sequence_id.asc())
        .limit(limit + 1)
    )
    rows = list(await session.scalars(stmt))
    has_more = len(rows) > limit
    page = rows[:limit]

    max_sequence_id = since_sequence_id
    items: list[SyncPullReportItem] = []
    for r in page:
        max_sequence_id = max(max_sequence_id, r.server_sequence_id)
        items.append(
            SyncPullReportItem(
                id=r.id,
                kind=r.kind,
                segment_key=r.segment_key,
                status=r.status,
                payload=r.payload,
                created_at=r.created_at,
                updated_at=r.updated_at,
                deleted_at=r.deleted_at,
                source_gateway_id=r.source_gateway_id,
                server_sequence_id=r.server_sequence_id,
                is_tombstone=r.is_tombstone,
            )
        )

    latest_row = await session.scalar(
        select(ModelArtifact)
        .where(ModelArtifact.is_latest.is_(True))
        .order_by(ModelArtifact.name.asc())
        .limit(1)
    )
    latest_meta: LatestModelVersionMeta | None = None
    if latest_row is not None:
        latest_meta = LatestModelVersionMeta(
            name=latest_row.name,
            version=latest_row.version,
            sha256=latest_row.file_sha256,
            size_bytes=latest_row.file_size_bytes,
            min_gateway_version=latest_row.min_gateway_version,
            input_schema_hash=latest_row.input_schema_hash,
        )

    return SyncPullResponse(
        items=items,
        max_sequence_id=max_sequence_id,
        has_more=has_more,
        latest_model_version=latest_meta,
    )
