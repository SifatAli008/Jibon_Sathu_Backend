#!/usr/bin/env python3
"""
Export placeholder sklearn RandomForest to ONNX (Issue #3).

Requires dev install: pip install -e ".[dev]"

Example:
  python scripts/export_road_decay_onnx.py --output-dir artifacts/models
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export road_decay placeholder ONNX")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/models"),
        help="Directory to write road_decay_model.onnx",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Override suggested version string (default: UTC date-based)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from app.ml.onnx_export import export_road_decay_model

    out = export_road_decay_model(args.output_dir, version_override=args.version)
    payload = {
        "output_path": str(out.output_path.resolve()),
        "sha256": out.sha256_hex,
        "suggested_version": out.suggested_version,
        "size_bytes": out.file_size_bytes,
    }
    print(json.dumps(payload, indent=2))
    print(
        "\nNext: register as latest in Postgres (after migrations), e.g.\n"
        f"  python scripts/publish_model.py road_decay_model "
        f"--version {out.suggested_version} --file {out.output_path}\n",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
