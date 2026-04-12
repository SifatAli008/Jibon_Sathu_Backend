from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps.gateway_auth import require_gateway_for_models
from app.models import Gateway, ModelArtifact
from app.schemas.models import ModelLatestResponse
from app.services.model_paths import resolve_under_base
from app.services.model_publish import publish_new_latest

router = APIRouter()

_SLUG = re.compile(r"^[a-zA-Z0-9_.-]+$")
_MAX_PUBLISH_BYTES = 50 * 1024 * 1024


def _require_download_key(x_model_download_key: str | None) -> None:
    key = get_settings().models_download_key
    if not key:
        return
    if not x_model_download_key or x_model_download_key != key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid download key")


def _require_admin_key(x_models_admin_key: str | None) -> None:
    key = get_settings().models_admin_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publishing disabled")
    if not x_models_admin_key or x_models_admin_key != key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")


@router.get("/{name}/latest", response_model=ModelLatestResponse)
async def get_model_latest(
    name: str,
    session: AsyncSession = Depends(get_db),
    _gateway: Gateway | None = Depends(require_gateway_for_models),
) -> ModelLatestResponse:
    _ = _gateway
    if not _SLUG.match(name):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid model name")
    row = await session.scalar(
        select(ModelArtifact).where(ModelArtifact.name == name, ModelArtifact.is_latest.is_(True))
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no published model for this name")
    return ModelLatestResponse(
        name=row.name,
        version=row.version,
        sha256=row.file_sha256,
        size_bytes=row.file_size_bytes,
        updated_at=row.created_at,
    )


@router.get("/{name}/latest/file", response_model=None)
async def download_model_latest(
    name: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _gateway: Gateway | None = Depends(require_gateway_for_models),
    x_model_download_key: Annotated[str | None, Header(alias="X-Model-Download-Key")] = None,
) -> FileResponse | Response:
    _ = _gateway
    _require_download_key(x_model_download_key)
    if not _SLUG.match(name):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid model name")

    row = await session.scalar(
        select(ModelArtifact).where(ModelArtifact.name == name, ModelArtifact.is_latest.is_(True))
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no published model for this name")

    inm = request.headers.get("if-none-match")
    if inm:
        clean = inm.strip().strip('"')
        if clean.lower() == row.file_sha256.lower():
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    base = Path(get_settings().model_artifacts_base_dir).resolve()
    try:
        abs_path = resolve_under_base(base, row.storage_path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    if not abs_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact file missing on disk")

    etag = f'"{row.file_sha256}"'
    fname = f"{name}-{row.version}.onnx"
    return FileResponse(
        path=str(abs_path),
        media_type="application/octet-stream",
        filename=fname,
        headers={
            "ETag": etag,
            "Content-Disposition": f'attachment; filename="{fname}"',
        },
    )


@router.post(
    "/{name}/publish",
    status_code=status.HTTP_201_CREATED,
    response_model=ModelLatestResponse,
)
async def publish_model_version(
    name: str,
    version: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    x_models_admin_key: Annotated[str | None, Header(alias="X-Models-Admin-Key")] = None,
    session: AsyncSession = Depends(get_db),
) -> ModelLatestResponse:
    _require_admin_key(x_models_admin_key)
    if not _SLUG.match(name) or not _SLUG.match(version):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid name or version")
    data = await file.read()
    if len(data) > _MAX_PUBLISH_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large")
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="empty file")

    base = Path(get_settings().model_artifacts_base_dir).resolve()
    rel = f"{name}/{version}.onnx"
    try:
        async with session.begin():
            row = await publish_new_latest(
                session, base_dir=base, name=name, version=version, data=data
            )
    except IntegrityError as e:
        try:
            resolve_under_base(base, rel).unlink(missing_ok=True)
        except ValueError:
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="publish failed (duplicate version or constraint violation)",
        ) from e

    return ModelLatestResponse(
        name=row.name,
        version=row.version,
        sha256=row.file_sha256,
        size_bytes=row.file_size_bytes,
        updated_at=row.created_at,
    )
