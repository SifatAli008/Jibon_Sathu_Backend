"""Gateway authentication dependency (Issue #7)."""

from __future__ import annotations

import secrets
from typing import Annotated
from uuid import UUID

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Gateway


def hash_gateway_secret(secret: str) -> str:
    """Store only a bcrypt hash of the shared secret (never the raw secret)."""
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_gateway_secret(secret: str, secret_hash: str) -> bool:
    try:
        return bcrypt.checkpw(secret.encode("utf-8"), secret_hash.encode("ascii"))
    except ValueError:
        return False


async def _authenticate_gateway_bearer(
    session: AsyncSession, x_gateway_id: UUID, authorization: str | None
) -> Gateway:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token")

    row = await session.get(Gateway, x_gateway_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown gateway")

    if row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gateway revoked")

    if not row.auth_secret_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gateway not provisioned (missing auth_secret_hash)",
        )

    if not verify_gateway_secret(token, row.auth_secret_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid gateway secret")

    return row


async def require_sync_gateway_id(
    x_gateway_id: Annotated[UUID, Header(alias="X-Gateway-Id")],
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_db),
) -> UUID:
    """
    Validates sync identity.

    When `REQUIRE_GATEWAY_AUTH=false`, this performs **no DB writes** (avoid nested transactions with
    `POST /sync/push`). The merge path still upserts `gateways` as needed.
    """
    settings = get_settings()
    if not settings.require_gateway_auth:
        return x_gateway_id

    row = await _authenticate_gateway_bearer(session, x_gateway_id, authorization)
    return row.id


async def require_gateway_for_models(
    x_gateway_id: Annotated[UUID | None, Header(alias="X-Gateway-Id")] = None,
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_db),
) -> Gateway | None:
    """
    Issue #7: when `REQUIRE_GATEWAY_AUTH=true`, model metadata/download routes require the same
    bearer flow as sync. When auth is disabled, behave like Issue #3 (no gateway headers required).
    """
    settings = get_settings()
    if not settings.require_gateway_auth:
        return None
    if x_gateway_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Gateway-Id")
    return await _authenticate_gateway_bearer(session, x_gateway_id, authorization)


async def require_sync_admin(
    x_sync_admin_key: Annotated[str | None, Header(alias="X-Sync-Admin-Key")] = None,
) -> None:
    key = get_settings().sync_admin_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conflicts endpoint disabled")
    if not x_sync_admin_key or not secrets.compare_digest(x_sync_admin_key, key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid sync admin key")
