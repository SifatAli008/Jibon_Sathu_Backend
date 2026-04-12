"""Dashboard analytics (Issue #13)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps.dashboard_auth import require_dashboard_admin
from app.services import analytics_service

router = APIRouter()


@router.get("/map-layers")
async def map_layers(
    _: None = Depends(require_dashboard_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    cached = analytics_service.analytics_cache_get("jibon:analytics:map-layers:v1")
    if cached:
        return json.loads(cached.decode("utf-8"))
    data = await analytics_service.build_map_layers_geojson(session)
    raw = json.dumps(data).encode("utf-8")
    analytics_service.analytics_cache_set("jibon:analytics:map-layers:v1", raw)
    return data


@router.get("/sos-queue")
async def sos_queue(
    _: None = Depends(require_dashboard_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    items = await analytics_service.build_sos_queue(session)
    return {"items": items, "count": len(items)}
