#!/usr/bin/env python3
"""
Register an ONNX file as the latest version for a model name (Issue #3).

Uses DATABASE_URL (asyncpg URL is fine). Requires migrations applied.

Example:
  python scripts/publish_model.py road_decay_model --version 2026.04.12-1 --file artifacts/models/road_decay_model.onnx
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def _publish(name: str, version: str, file_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings
    from app.services.model_publish import publish_new_latest

    get_settings.cache_clear()
    settings = get_settings()
    data = file_path.read_bytes()
    base = Path(settings.model_artifacts_base_dir).resolve()

    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            async with session.begin():
                await publish_new_latest(
                    session, base_dir=base, name=name, version=version, data=data
                )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish ONNX as latest model_artifacts row")
    parser.add_argument("name", help="Model name, e.g. road_decay_model")
    parser.add_argument("--version", required=True, help="Version string, e.g. 2026.04.12-1")
    parser.add_argument("--file", type=Path, required=True, help="Path to .onnx file")
    args = parser.parse_args()
    asyncio.run(_publish(args.name, args.version, args.file))
    print("Published OK:", args.name, args.version)


if __name__ == "__main__":
    main()
