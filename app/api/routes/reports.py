from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Report

router = APIRouter()


class ReportReadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    segment_key: str | None
    payload: dict
    created_at: str
    updated_at: str
    source_gateway_id: UUID | None
    deleted_at: str | None = None


@router.get("/reports", response_model=list[ReportReadOut])
async def list_reports_dev(
    session: AsyncSession = Depends(get_db),
    x_dev_reports_key: Annotated[str | None, Header(alias="X-Dev-Reports-Key")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ReportReadOut]:
    key = get_settings().reports_dev_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not x_dev_reports_key or x_dev_reports_key != key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    result = await session.scalars(select(Report).order_by(Report.updated_at.desc()).limit(limit))
    rows = list(result)
    out: list[ReportReadOut] = []
    for r in rows:
        out.append(
            ReportReadOut(
                id=r.id,
                kind=r.kind,
                status=r.status,
                segment_key=r.segment_key,
                payload=r.payload,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat(),
                source_gateway_id=r.source_gateway_id,
                deleted_at=r.deleted_at.isoformat() if r.deleted_at else None,
            )
        )
    return out
