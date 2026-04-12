"""Dashboard / analytics API key (Issue #13)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_dashboard_admin(
    x_dashboard_admin_key: Annotated[str | None, Header(alias="X-Dashboard-Admin-Key")] = None,
) -> None:
    key = get_settings().dashboard_admin_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="analytics disabled")
    if not x_dashboard_admin_key or not secrets.compare_digest(x_dashboard_admin_key, key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid dashboard admin key")
