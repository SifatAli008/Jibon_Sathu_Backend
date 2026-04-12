"""Resolve artifact paths under the configured base directory (no path traversal)."""

from __future__ import annotations

from pathlib import Path


def resolve_under_base(base_dir: Path, storage_path: str) -> Path:
    if not storage_path or storage_path.startswith(("/", "\\")):
        raise ValueError("storage_path must be relative")
    rel = Path(storage_path)
    if ".." in rel.parts:
        raise ValueError("invalid storage_path")
    base_res = base_dir.resolve()
    out = (base_res / rel).resolve()
    try:
        out.relative_to(base_res)
    except ValueError as e:
        raise ValueError("path escapes base directory") from e
    return out
