from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.sync import SyncPushRequest, SyncPushResponse
from app.services.merge_service import BatchValidationError, SimulatedMergeFault
from app.services.sync_push import process_sync_push

router = APIRouter()


@router.post("/push", response_model=SyncPushResponse)
async def sync_push(
    x_gateway_id: Annotated[UUID, Header(alias="X-Gateway-Id")],
    x_sync_batch_id: Annotated[UUID, Header(alias="X-Sync-Batch-Id")],
    body: SyncPushRequest,
    session: AsyncSession = Depends(get_db),
) -> SyncPushResponse:
    try:
        async with session.begin():
            return await process_sync_push(session, body, x_gateway_id, x_sync_batch_id)
    except BatchValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except SimulatedMergeFault as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
