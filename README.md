# Jibon Sathu Backend

Zone A (cloud) FastAPI service: Postgres schema, health check, and **`POST /v1/sync/push`** (frozen v1 contract).

**Local run + client integration:** [docs/startup-guide.md](docs/startup-guide.md) · **HTTP route list:** [docs/api-endpoints.md](docs/api-endpoints.md)

## Quick start

1. Start Postgres: `docker compose up -d` (published on host **`127.0.0.1:5433`** — see `docker-compose.yml`).
2. `python -m venv .venv` then activate and `pip install -e ".[dev]"`
3. Copy `.env.example` to `.env` and adjust if needed. If you already have a `.env`, set **`DATABASE_URL`** to use port **5433** and user/password **`jibon`/`jibon`** unless you changed them in Compose.
4. `alembic upgrade head` (re-run after pulling new migrations, e.g. `model_artifacts` for ONNX — Issue #3).
5. `uvicorn app.main:app --reload`

### Still seeing `password authentication failed for user "jibon"`?

- **Wrong process on the port:** An older `.env` may still point at **`5432`**, which is often a **system PostgreSQL**, not this project’s container. Prefer **`127.0.0.1:5433`** as in `.env.example`.
- **Stale Docker volume:** If you ever changed `POSTGRES_*` in Compose, Postgres keeps the old data directory. Reset with:

  `docker compose down -v` then `docker compose up -d`

  (**`-v` deletes the DB volume** — only do this if you do not need that data.)

### `localhost` vs `127.0.0.1` (Windows)

`localhost` can resolve to IPv6 (`::1`) first; another Postgres may listen there. This repo defaults to **`127.0.0.1`** in connection examples.

## Tests

With Postgres running and `DATABASE_URL` set (see `.env.example`):

```bash
pytest
# ONNX + compatibility metadata (Issue #9) — requires dev ML stack:
pytest tests/test_models_onnx.py -q
# Optional analytics load check (Issue #13) — seeds 10k rows; requires Postgres:
# set RUN_ANALYTICS_LOAD_TEST=1
# pytest tests/test_analytics_load.py -q
```

API tests use `httpx.AsyncClient` (async) so the same event loop owns asyncpg for the whole test. For local verification of merge behavior, set `REPORTS_DEV_KEY` and call `GET /reports` with header `X-Dev-Reports-Key` (see `API_SPEC.md`).

## ONNX model distribution (Issue #3)

**Export** (requires `pip install -e ".[dev]"` for sklearn / skl2onnx / onnx):

```bash
python scripts/export_road_decay_onnx.py --output-dir artifacts/models
```

The script prints `sha256`, `suggested_version`, `size_bytes`, and a mock **`min_gateway_version`** (e.g. `1.0.0`).

**Publish** (writes under `MODEL_ARTIFACTS_BASE_DIR`, default `artifacts/models`, and updates Postgres):

1. Apply migrations: `alembic upgrade head`
2. `python scripts/publish_model.py road_decay_model --version <version-from-export> --min-gateway-version 1.0.0 --file artifacts/models/road_decay_model.onnx`  
   Optional: `--input-schema-hash <64-char-hex>` when the ONNX IO contract changes.

**HTTP API** (see `API_SPEC.md`): `GET /v1/models/{name}/latest` (metadata incl. `min_gateway_version`), `GET /v1/models/{name}/latest/file` (binary via `FileResponse`, `ETag` = SHA256 for conditional GET).

**Optional auth:** set `MODELS_DOWNLOAD_KEY` to require header `X-Model-Download-Key` on **file** download only. Set `MODELS_ADMIN_KEY` and use header `X-Models-Admin-Key` on **`POST /v1/models/{name}/publish`** (multipart: `version`, **`min_gateway_version`**, optional `input_schema_hash`, `file`) for in-band publishing without the CLI.

**Ops:** The API process does not cache file contents; new publishes are visible immediately. Back up `MODEL_ARTIFACTS_BASE_DIR` and the database together when promoting releases.

## Disaster-mode client backoff (Issues #5–#8)

When many gateways reconnect at once, Zone A may respond with **429 Too Many Requests** on `/v1/sync/*`. Clients should:

- Honor **`Retry-After`** (seconds) when present.
- Otherwise use exponential backoff with jitter (e.g., base 250ms, cap ~60s), and avoid tight loops that amplify congestion.
- Treat **413 Payload Too Large** as a hard batching error: split work into smaller pushes (default server max is **500** reports per request).

See `API_SPEC.md` for tombstone/pull semantics and `SECURITY_MODEL.md` for gateway provisioning.

## Gateway integration spike (Issue #4)

End-to-end rehearsal (push overlapping reports → optional dev `GET /reports` → model metadata → download → SHA256 + onnxruntime):

```bash
# Terminal A: API + Postgres (see Quick start). Publish a model first (Issue #3).
# Terminal B:
pip install -e ".[dev]"
python tools/gateway_sim.py --base-url http://127.0.0.1:8000 --repeat-idempotent-push
```

Optional env vars: `GATEWAY_SIM_GATEWAY_ID`, `GATEWAY_SIM_MODEL_NAME` (default `road_decay_model`), `GATEWAY_SIM_DOWNLOAD_KEY`, `GATEWAY_SIM_REPORTS_KEY` (for `GET /reports` when `REPORTS_DEV_KEY` is set on the server). CLI: `--sleep-ms`, `--sleep-before-push-ms`, `--no-verify-tls`, `--timeout`.

Artifacts: [docs/gateway-spike-sequence.md](docs/gateway-spike-sequence.md), [docs/gateway-spike-network-notes.md](docs/gateway-spike-network-notes.md), [docs/samples/gateway-spike-run.txt](docs/samples/gateway-spike-run.txt), [report/issue-04-implementation-report.md](report/issue-04-implementation-report.md).

## Background triage (Issue #11)

Merge commits stay fast: **`POST /v1/sync/push`** enqueues **`triage_reports_task`** after the transaction commits. Workers run **`app.tasks.triage`** against Postgres (sync URL) and update `reports.triage_status` / `priority_score`.

- **Docker:** `docker compose` includes **Redis** on the internal network (and maps host `6379` if you use the published port).
- **Env:** `CELERY_BROKER_URL` (and optional `CELERY_RESULT_BACKEND`). For local tests without Redis, set **`CELERY_TASK_ALWAYS_EAGER=true`** (the app uses an in-memory Celery broker/backend so `pytest` does not require Redis).
- **Run worker:** `celery -A app.worker worker -l info` (same Python env and `DATABASE_URL` / sync URL as the API).

## gRPC ingest (Issue #12)

**`SyncIngest.PushBatch`** mirrors **`POST /v1/sync/push`** (same `MergeService` rules). Proto: `protos/sync.proto`; regenerate stubs with `python scripts/gen_grpc_stubs.py`.

- **Env:** `GRPC_PORT` (default **50051**; set **`0`** to disable the in-process server). Clients must send **`x-client-version`** (or `x-gateway-version`) metadata ≥ **`GRPC_MIN_CLIENT_VERSION`** (default `1.0.0`).

## Dashboard analytics (Issue #13)

**`GET /v1/analytics/map-layers`** (GeoJSON-style) and **`GET /v1/analytics/sos-queue`** power the React dashboard. When **`DASHBOARD_ADMIN_KEY`** is set, send **`X-Dashboard-Admin-Key`**. Optional Redis caching uses the same URL as **`CELERY_BROKER_URL`** (`ANALYTICS_CACHE_TTL_SECONDS`).

**CORS:** `app/main.py` allows common dev origins for the React app; tighten for production.

See `API_SPEC.md` and `SECURITY_MODEL.md`.
