#!/usr/bin/env python3
"""Regenerate gRPC Python stubs (Issue #12).

Requires: pip install grpcio-tools

Usage (from repo root):

  python scripts/gen_grpc_stubs.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    protos = root / "protos"
    out = root / "app" / "grpc_gen"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        "-I",
        str(protos),
        f"--python_out={out}",
        f"--grpc_python_out={out}",
        str(protos / "sync.proto"),
    ]
    subprocess.check_call(cmd)
    # Fix relative import in generated grpc file for package layout
    grpc_py = out / "sync_pb2_grpc.py"
    text = grpc_py.read_text(encoding="utf-8")
    text = text.replace("import sync_pb2 as sync__pb2", "from . import sync_pb2 as sync__pb2")
    grpc_py.write_text(text, encoding="utf-8")
    print("ok:", grpc_py)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
