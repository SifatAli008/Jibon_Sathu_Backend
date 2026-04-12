from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps.gateway_auth import require_sync_admin, require_sync_gateway_id
from app.limits import limiter
from app.models import SyncLog
from app.schemas.sync import SyncConflictsResponse, SyncConflictLogItem, SyncPullResponse, SyncPushRequest, SyncPushResponse
from app.services.merge_service import (
    BatchPayloadTooLargeError,
    BatchValidationError,
    SimulatedMergeFault,
)
from app.services.sync_push import process_sync_push
from app.services.sync_pull import build_sync_pull_response

router = APIRouter()


@router.post("/push", response_model=SyncPushResponse)
@limiter.limit(get_settings().sync_rate_limit)
async def sync_push(
    request: Request,
    gateway_id: Annotated[UUID, Depends(require_sync_gateway_id)],
    x_sync_batch_id: Annotated[UUID, Header(alias="X-Sync-Batch-Id")],
    body: SyncPushRequest,
    session: AsyncSession = Depends(get_db),
) -> SyncPushResponse:
    _ = request
    try:
        async with session.begin():
            return await process_sync_push(session, body, gateway_id, x_sync_batch_id)
    except BatchPayloadTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e)) from e
    except BatchValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except SimulatedMergeFault as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/pull", response_model=SyncPullResponse)
@limiter.limit(get_settings().sync_rate_limit)
async def sync_pull(
    request: Request,
    gateway_id: Annotated[UUID, Depends(require_sync_gateway_id)],
    session: AsyncSession = Depends(get_db),
    since_sequence_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SyncPullResponse:
    _ = request
    _ = gateway_id
    return await build_sync_pull_response(
        session, since_sequence_id=since_sequence_id, limit=limit
    )


@router.get("/conflicts", response_model=SyncConflictsResponse)
@limiter.limit(get_settings().sync_rate_limit)
async def sync_conflicts(
    request: Request,
    _: Annotated[None, Depends(require_sync_admin)],
    session: AsyncSession = Depends(get_db),
    since_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SyncConflictsResponse:
    _ = request
    stmt = (
        select(SyncLog)
        .where(SyncLog.id > since_id)
        .order_by(SyncLog.id.asc())
        .limit(limit + 1)
    )
    rows = list(await session.scalars(stmt))
    has_more = len(rows) > limit
    page = rows[:limit]
    items = [
        SyncConflictLogItem(
            id=r.id,
            gateway_id=r.gateway_id,
            batch_id=r.batch_id,
            received_at=r.received_at,
            record_count=r.record_count,
            applied_count=r.applied_count,
            status=r.status,
            server_sequence_id=r.server_sequence_id,
            merge_audit=r.merge_audit,
        )
        for r in page
    ]
    return SyncConflictsResponse(items=items, has_more=has_more)
