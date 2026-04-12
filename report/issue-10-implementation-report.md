# Implementation report — Issue #10 (API versioning — `/v1` contract freeze)

**Date:** 2026-04-12  
**Dependencies:** Issue #9.

---

## Deliverables

| Item | Status | Location |
|------|--------|----------|
| Sync + models under `/v1/` | **Done** | `app/api/routes/__init__.py` (`v1_router`) |
| `/health` at root | **Done** | `health` router on `api_router` without prefix |
| Dev `/reports` at root | **Done** | unchanged |
| Legacy `/sync/*` without prefix → **404** | **Done** | no unversioned sync routes mounted |
| Scripts updated | **Done** | `tools/gateway_sim.py`, `scripts/publish_model.py` (CLI paths N/A; HTTP examples in README) |
| CORS + SlowAPI | **Done** | `app/main.py` (CORS outermost; slowapi `app.state.limiter` unchanged) |
| Tests | **Done** | `tests/test_api.py`, `tests/test_issues_5_8.py`, `tests/test_models_onnx.py` use `/v1/...` |
| Docs | **Done** | `API_SPEC.md`, `README.md` |

---

## Gateway sim

```bash
python tools/gateway_sim.py --base-url http://127.0.0.1:8000
```

Calls `POST /v1/sync/push`, `GET /v1/models/{name}/latest`, and `GET /v1/models/{name}/latest/file`.

---

## Contract rule

Only **`/v1/sync/*`** and **`/v1/models/*`** are part of the frozen edge contract; unversioned sync/model URLs are intentionally absent.
