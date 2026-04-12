"""
Export a tiny sklearn model to ONNX for gateway distribution (Issue #3).

Imports sklearn / skl2onnx lazily so production `pip install` without ML extras still starts the API.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    sha256_hex: str
    file_size_bytes: int
    suggested_version: str


def export_road_decay_model(
    output_dir: Path,
    *,
    version_override: str | None = None,
    filename: str = "road_decay_model.onnx",
) -> ExportResult:
    import numpy as np
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    from sklearn.ensemble import RandomForestRegressor

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    x = rng.standard_normal((200, 4)).astype(np.float32)
    coef = np.array([0.1, -0.2, 0.4, 0.05], dtype=np.float32)
    y = (x @ coef + 0.01 * rng.standard_normal(200)).astype(np.float32)

    reg = RandomForestRegressor(n_estimators=8, max_depth=4, random_state=42)
    reg.fit(x, y)

    initial_types = [("float_input", FloatTensorType([None, 4]))]
    onnx_model = convert_sklearn(reg, initial_types=initial_types, target_opset=17)
    content = onnx_model.SerializeToString()

    out_path = output_dir / filename
    out_path.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    ver = version_override or datetime.now(UTC).strftime("%Y.%m.%d-1")
    return ExportResult(
        output_path=out_path,
        sha256_hex=sha,
        file_size_bytes=len(content),
        suggested_version=ver,
    )
