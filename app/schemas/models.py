from datetime import datetime

from pydantic import BaseModel, Field


class ModelLatestResponse(BaseModel):
    name: str
    version: str
    sha256: str
    size_bytes: int
    updated_at: datetime = Field(description="Promotion time (`created_at` in DB).")
    min_gateway_version: str = Field(description="Minimum Zone B gateway app semver this artifact supports.")
    input_schema_hash: str | None = Field(
        default=None,
        description="Stable hash of ONNX input schema / feature contract (nullable if unchanged).",
    )

    model_config = {"json_schema_extra": {"example": {
        "name": "road_decay_model",
        "version": "2026.04.12-1",
        "sha256": "ab" * 32,
        "size_bytes": 1234,
        "updated_at": "2026-04-12T12:00:00+00:00",
        "min_gateway_version": "1.0.0",
        "input_schema_hash": "a" * 64,
    }}}
