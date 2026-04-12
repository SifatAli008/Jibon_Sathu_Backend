from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app
from app.ml.onnx_export import export_road_decay_model


@pytest.fixture
async def ac() -> AsyncClient:
    from app.db import dispose_db_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await dispose_db_engine()


def _publish_form(version: str) -> dict:
    return {
        "version": version,
        "min_gateway_version": "1.0.0",
        "input_schema_hash": "ab" * 32,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_metadata_download_onnx_infer(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MODELS_ADMIN_KEY", "adm-secret")
    monkeypatch.setenv("MODEL_ARTIFACTS_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    mname = f"road_decay_{uuid.uuid4().hex[:10]}"
    build = tmp_path / "build"
    ex = export_road_decay_model(build, version_override=f"test-{uuid.uuid4().hex[:10]}")
    onnx_bytes = ex.output_path.read_bytes()

    pr = await ac.post(
        f"/v1/models/{mname}/publish",
        data=_publish_form(ex.suggested_version),
        files={"file": ("model.onnx", onnx_bytes, "application/octet-stream")},
        headers={"X-Models-Admin-Key": "adm-secret"},
    )
    assert pr.status_code == 201, pr.text
    meta = pr.json()
    assert meta["sha256"] == ex.sha256_hex
    assert meta["size_bytes"] == ex.file_size_bytes
    assert meta["min_gateway_version"] == "1.0.0"
    assert meta["input_schema_hash"] == "ab" * 32

    gr = await ac.get(f"/v1/models/{mname}/latest")
    assert gr.status_code == 200
    latest = gr.json()
    assert latest["sha256"] == ex.sha256_hex
    assert latest["min_gateway_version"] == "1.0.0"

    dr = await ac.get(f"/v1/models/{mname}/latest/file")
    assert dr.status_code == 200
    assert len(dr.content) == ex.file_size_bytes
    assert dr.headers.get("etag", "").strip('"').lower() == ex.sha256_hex.lower()

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as tf:
        tf.write(dr.content)
        tf.flush()
        path = tf.name
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    try:
        inp = sess.get_inputs()[0].name
        out = sess.run(None, {inp: np.random.randn(1, 4).astype(np.float32)})
        assert len(out) >= 1
    finally:
        os.unlink(path)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_missing_min_gateway_version_422(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MODELS_ADMIN_KEY", "adm-secret")
    monkeypatch.setenv("MODEL_ARTIFACTS_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    mname = f"road_decay_{uuid.uuid4().hex[:10]}"
    ex = export_road_decay_model(tmp_path / "b", version_override=f"missing-{uuid.uuid4().hex[:8]}")
    body = ex.output_path.read_bytes()
    pr = await ac.post(
        f"/v1/models/{mname}/publish",
        data={"version": ex.suggested_version},
        files={"file": ("m.onnx", body, "application/octet-stream")},
        headers={"X-Models-Admin-Key": "adm-secret"},
    )
    assert pr.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_model_cli_matches_latest_route(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Script-based publish + HTTP GET /v1/models/.../latest (Issue #9 E2E)."""
    monkeypatch.setenv("MODEL_ARTIFACTS_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    mname = f"cli_{uuid.uuid4().hex[:10]}"
    ex = export_road_decay_model(tmp_path / "cli", version_override=f"cli-{uuid.uuid4().hex[:8]}")
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    r = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "publish_model.py"),
            mname,
            "--version",
            ex.suggested_version,
            "--min-gateway-version",
            "2.1.0",
            "--input-schema-hash",
            "deadbeef" * 8,
            "--file",
            str(ex.output_path),
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout

    lr = await ac.get(f"/v1/models/{mname}/latest")
    assert lr.status_code == 200, lr.text
    j = lr.json()
    assert j["version"] == ex.suggested_version
    assert j["min_gateway_version"] == "2.1.0"
    assert j["input_schema_hash"] == "deadbeef" * 8


@pytest.mark.integration
@pytest.mark.asyncio
async def test_download_etag_returns_304(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MODELS_ADMIN_KEY", "adm-secret")
    monkeypatch.setenv("MODEL_ARTIFACTS_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    mname = f"road_decay_{uuid.uuid4().hex[:10]}"
    ex = export_road_decay_model(tmp_path / "b", version_override=f"t304-{uuid.uuid4().hex[:8]}")
    body = ex.output_path.read_bytes()
    assert (
        await ac.post(
            f"/v1/models/{mname}/publish",
            data=_publish_form(ex.suggested_version),
            files={"file": ("m.onnx", body, "application/octet-stream")},
            headers={"X-Models-Admin-Key": "adm-secret"},
        )
    ).status_code == 201

    r1 = await ac.get(f"/v1/models/{mname}/latest/file")
    assert r1.status_code == 200
    etag = r1.headers["etag"]
    r2 = await ac.get(f"/v1/models/{mname}/latest/file", headers={"If-None-Match": etag})
    assert r2.status_code == 304


@pytest.mark.integration
@pytest.mark.asyncio
async def test_download_requires_key_when_configured(
    ac: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MODELS_ADMIN_KEY", "adm-secret")
    monkeypatch.setenv("MODELS_DOWNLOAD_KEY", "dl-secret")
    monkeypatch.setenv("MODEL_ARTIFACTS_BASE_DIR", str(tmp_path))
    get_settings.cache_clear()

    mname = f"road_decay_{uuid.uuid4().hex[:10]}"
    ex = export_road_decay_model(tmp_path / "c", version_override=f"dlk-{uuid.uuid4().hex[:8]}")
    pr = await ac.post(
        f"/v1/models/{mname}/publish",
        data=_publish_form(ex.suggested_version),
        files={"file": ("m.onnx", ex.output_path.read_bytes(), "application/octet-stream")},
        headers={"X-Models-Admin-Key": "adm-secret"},
    )
    assert pr.status_code == 201, pr.text

    assert (await ac.get(f"/v1/models/{mname}/latest/file")).status_code == 401
    ok = await ac.get(
        f"/v1/models/{mname}/latest/file",
        headers={"X-Model-Download-Key": "dl-secret"},
    )
    assert ok.status_code == 200
