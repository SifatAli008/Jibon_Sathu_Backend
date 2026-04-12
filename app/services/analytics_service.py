"""Read-side aggregations for dashboard (Issue #13)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Report


def _coords(payload: dict[str, Any]) -> tuple[float, float] | None:
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        return None
    try:
        return (float(lat), float(lon))
    except (TypeError, ValueError):
        return None


async def build_map_layers_geojson(session: AsyncSession) -> dict[str, Any]:
    """GeoJSON FeatureCollection for non-tombstone road/supply with lat/lon."""
    stmt = (
        select(Report)
        .where(Report.is_tombstone.is_(False))
        .where(Report.kind.in_(("road", "supply")))
        .order_by(Report.server_sequence_id.desc())
        .limit(5000)
    )
    rows = list(await session.scalars(stmt))
    features: list[dict[str, Any]] = []
    for r in rows:
        coords = _coords(dict(r.payload or {}))
        if coords is None:
            continue
        lon, lat = coords[1], coords[0]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": str(r.id),
                    "kind": r.kind,
                    "status": r.status,
                    "segment_key": r.segment_key,
                    "updated_at": r.updated_at.isoformat(),
                    "priority_score": r.priority_score,
                    "triage_status": r.triage_status,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


async def build_sos_queue(session: AsyncSession, *, limit: int = 200) -> list[dict[str, Any]]:
    stmt = (
        select(Report)
        .where(Report.kind == "sos", Report.is_tombstone.is_(False))
        .order_by(Report.priority_score.desc().nulls_last(), Report.server_sequence_id.desc())
        .limit(limit)
    )
    rows = list(await session.scalars(stmt))
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": str(r.id),
                "status": r.status,
                "payload": dict(r.payload or {}),
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
                "priority_score": r.priority_score,
                "triage_status": r.triage_status,
                "server_sequence_id": r.server_sequence_id,
            }
        )
    return out


def analytics_cache_get(key: str) -> bytes | None:
    settings = get_settings()
    if not settings.celery_broker_url:
        return None
    try:
        import redis
    except ImportError:
        return None
    r = redis.Redis.from_url(settings.celery_broker_url, decode_responses=False)
    v = r.get(key)
    if v is None:
        return None
    return bytes(v)


def analytics_cache_set(key: str, value: bytes) -> None:
    settings = get_settings()
    if not settings.celery_broker_url:
        return
    try:
        import redis
    except ImportError:
        return
    r = redis.Redis.from_url(settings.celery_broker_url, decode_responses=False)
    r.setex(key, settings.analytics_cache_ttl_seconds, value)
