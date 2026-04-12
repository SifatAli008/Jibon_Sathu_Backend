# Implementation report — Issue #3 (ML model ONNX distribution)

**Reference:** [Dev docs/issue-03-ml-model-onnx-distribution-pipeline.md](../Dev%20docs/issue-03-ml-model-onnx-distribution-pipeline.md)  
**Date:** 2026-04-12  
**Depends on:** Issue #1 DB + app shell.

---

## Deliverables (Issue §8)

| Item | Status | Notes |
|------|--------|--------|
| sklearn placeholder + ONNX export | **Done** | `app/ml/onnx_export.py` (lazy ML imports), `scripts/export_road_decay_onnx.py` |
| DB + migration | **Done** | `model_artifacts` table, Alembic `20260412_0002`, partial unique index one `is_latest` per `name` |
| `GET .../latest` metadata | **Done** | `GET /models/{name}/latest` |
| `GET .../latest/file` binary | **Done** | `FileResponse`, `ETag` from SHA256, `Content-Disposition`, **304** on `If-None-Match` |
| Pytest + onnxruntime | **Done** | `tests/test_models_onnx.py` (publish, download, infer, ETag, optional download key) |
| README retrain section | **Done** | “ONNX model distribution” in `README.md` |

---

## API summary

- **Probe:** `GET /models/{name}/latest` → JSON `name`, `version`, `sha256`, `size_bytes`, `updated_at` (from `created_at`).
- **Download:** `GET /models/{name}/latest/file` — optional `MODELS_DOWNLOAD_KEY` + header `X-Model-Download-Key`.
- **Publish (dev/ops):** `POST /models/{name}/publish` multipart `version` + `file` when `MODELS_ADMIN_KEY` is set and header `X-Models-Admin-Key` matches; or use **`scripts/publish_model.py`** against `DATABASE_URL`.

---

## Dependencies

- **Runtime:** `python-multipart` (multipart forms).
- **Dev / export / tests:** `onnxruntime`, `onnx`, `scikit-learn`, `skl2onnx`, `numpy` (see `[project.optional-dependencies] dev`).

---

## Ops

- Binaries default under `MODEL_ARTIFACTS_BASE_DIR` (`artifacts/models`); large `*.onnx` files are gitignored (see `.gitignore`).
- After pulling this change, run **`alembic upgrade head`** before tests or publish.

---

## Handoff to Issue #4

Gateways should: `GET .../latest` → compare `sha256` → conditional `GET .../latest/file` → verify hash → `onnxruntime.InferenceSession` (see tests for a reference flow).
