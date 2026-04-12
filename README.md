# Jibon Sathu Backend

Zone A (cloud) FastAPI service: Postgres schema, health check, and `POST /sync/push`.

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
```

API tests use `httpx.AsyncClient` (async) so the same event loop owns asyncpg for the whole test. For local verification of merge behavior, set `REPORTS_DEV_KEY` and call `GET /reports` with header `X-Dev-Reports-Key` (see `API_SPEC.md`).

## ONNX model distribution (Issue #3)

**Export** (requires `pip install -e ".[dev]"` for sklearn / skl2onnx / onnx):

```bash
python scripts/export_road_decay_onnx.py --output-dir artifacts/models
```

The script prints `sha256`, `suggested_version`, and `size_bytes`.

**Publish** (writes under `MODEL_ARTIFACTS_BASE_DIR`, default `artifacts/models`, and updates Postgres):

1. Apply migrations: `alembic upgrade head`
2. `python scripts/publish_model.py road_decay_model --version <version-from-export> --file artifacts/models/road_decay_model.onnx`

**HTTP API** (see `API_SPEC.md`): `GET /models/{name}/latest` (metadata), `GET /models/{name}/latest/file` (binary via `FileResponse`, `ETag` = SHA256 for conditional GET).

**Optional auth:** set `MODELS_DOWNLOAD_KEY` to require header `X-Model-Download-Key` on **file** download only. Set `MODELS_ADMIN_KEY` and use header `X-Models-Admin-Key` on **`POST /models/{name}/publish`** (multipart: `version`, `file`) for in-band publishing without the CLI.

**Ops:** The API process does not cache file contents; new publishes are visible immediately. Back up `MODEL_ARTIFACTS_BASE_DIR` and the database together when promoting releases.

## Disaster-mode client backoff (Issues #5–#8)

When many gateways reconnect at once, Zone A may respond with **429 Too Many Requests** on `/sync/*`. Clients should:

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
