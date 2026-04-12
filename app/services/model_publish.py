"""Transactional publish of a new latest model artifact (Issue #3)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelArtifact
from app.services.model_paths import resolve_under_base


async def publish_new_latest(
    session: AsyncSession,
    *,
    base_dir: Path,
    name: str,
    version: str,
    data: bytes,
) -> ModelArtifact:
    """
    Writes bytes to `{base_dir}/{name}/{version}.onnx` and inserts the DB row as sole `is_latest` for `name`.
    Caller should run inside `async with session.begin():`.
    """
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)
    rel = f"{name}/{version}.onnx"
    abs_path = resolve_under_base(base_dir, rel)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(data)

    await session.execute(
        update(ModelArtifact).where(ModelArtifact.name == name).values(is_latest=False)
    )
    row = ModelArtifact(
        id=uuid4(),
        name=name,
        version=version,
        file_sha256=sha,
        file_size_bytes=size,
        storage_path=rel,
        is_latest=True,
    )
    session.add(row)
    await session.flush()
    return row
