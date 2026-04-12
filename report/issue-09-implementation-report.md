# Implementation report — Issue #9 (Model version compatibility guards)

**Date:** 2026-04-12  
**Dependencies:** Issue #8 complete.

---

## Deliverables

| Item | Status | Location |
|------|--------|----------|
| `min_gateway_version`, `input_schema_hash` on `model_artifacts` | **Done** | `app/models/model_artifact.py`, Alembic `20260412_0005_model_compatibility_metadata.py` |
| `POST .../publish` requires `min_gateway_version` | **Done** | `app/api/routes/models.py` (`Form(min_length=1)`) → **422** if missing |
| `GET .../latest` returns compatibility fields | **Done** | `app/schemas/models.py`, `ModelLatestResponse` |
| `GET /v1/sync/pull` `latest_model_version` block includes same fields | **Done** | `app/schemas/sync.py`, `app/services/sync_pull.py` |
| `scripts/export_road_decay_onnx.py` emits mock `min_gateway_version` | **Done** | JSON payload includes `"1.0.0"` |
| `scripts/publish_model.py` CLI | **Done** | `--min-gateway-version`, optional `--input-schema-hash` |
| Tests | **Done** | `tests/test_models_onnx.py` |
| Docs | **Done** | `API_SPEC.md`, `README.md` |

---

## Migrations

```bash
alembic upgrade head
```

Existing rows receive `min_gateway_version='0.0.0'` during migration; new publishes must supply an explicit value via API or CLI.

---

## Tests

```bash
pytest tests/test_models_onnx.py -q
```
