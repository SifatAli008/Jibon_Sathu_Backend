# Zone A backend — local startup guide

This guide helps you run the Jibon Sathu cloud API on your PC so **Zone B (Flutter)** gateways and the **React dashboard** can connect. The API is a FastAPI app (HTTP + optional gRPC) backed by PostgreSQL.

---

## What runs where

| Component | Default port | Who uses it |
|-----------|--------------|-------------|
| **HTTP API** (REST, OpenAPI) | `8000` | React dashboard, Flutter apps (HTTPSync), browser |
| **gRPC** (`SyncIngest`) | `50051` | Flutter field clients (optional; same merge rules as REST) |
| **PostgreSQL** | `5433` on the host (mapped from container `5432`) | API + Celery worker |
| **Redis** | `6379` | Celery broker for background triage (optional in dev) |

Use **`127.0.0.1`** in connection strings on Windows to avoid IPv6 (`localhost` → `::1`) hitting a different Postgres than Docker.

---

## Prerequisites

- **Python 3.11+** (3.14 works if your stack supports it)
- **Docker Desktop** (or Docker Engine) for Postgres + Redis
- **Git** (to clone the repo)

---

## 1. Start databases

From the project root:

```bash
docker compose up -d
```

This starts **Postgres** (`jibon` / `jibon` / database `jibon_sathu` on host port **5433**) and **Redis** (**6379**).

Check health:

```bash
docker compose ps
```

If you change Postgres credentials or ports in `docker-compose.yml`, update `DATABASE_URL` in `.env` to match.

---

## 2. Configure environment

```bash
copy .env.example .env
```

Minimum for local development:

- **`DATABASE_URL`** — default in `.env.example` matches Compose (`127.0.0.1:5433`).

Recommended when integrating real clients:

| Variable | Purpose |
|----------|---------|
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` — enables async triage after sync (start a worker; see below). |
| `GRPC_PORT` | `50051` — enable gRPC for Flutter; use `0` to disable. |
| `DASHBOARD_ADMIN_KEY` | Shared secret; React sends `X-Dashboard-Admin-Key` for `/v1/analytics/*`. |
| `REPORTS_DEV_KEY` | Enables `GET /reports` (dev); React uses `VITE_DEV_REPORTS_KEY` for field devices + recent activity. |
| `SYNC_ADMIN_KEY` | Enables `GET /v1/sync/conflicts`; React uses `VITE_SYNC_ADMIN_KEY` for sync history. |
| `REQUIRE_GATEWAY_AUTH` | Leave `false` for quick local tests; set `true` in production and provision gateways (see `SECURITY_MODEL.md`). |

Details for all keys: `.env.example`, `SECURITY_MODEL.md`, and [api-endpoints.md](api-endpoints.md).

---

## 3. Install Python dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

---

## 4. Apply database migrations

```bash
alembic upgrade head
```

Re-run this after pulling migrations from git.

---

## 5. Run the API

**Default (localhost only):**

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Phones / emulators / another machine on the LAN** must reach your PC’s IP. Bind on all interfaces:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then use `http://<your-LAN-IP>:8000` from the Flutter app or dashboard (same Wi‑Fi; allow the port in Windows Firewall if needed).

- **Interactive docs:** `http://127.0.0.1:8000/docs` (Swagger UI)
- **OpenAPI JSON:** `http://127.0.0.1:8000/openapi.json`

---

## 6. Optional: Celery worker (background triage)

If `CELERY_BROKER_URL` is set, enqueueing runs after each successful sync. Start a worker in a **second terminal** (same venv and working directory):

```bash
celery -A app.worker worker -l info
```

Without Redis/worker, sync still works; `reports.triage_status` may stay `pending` until a worker processes jobs.

For **tests only**, you can use `CELERY_TASK_ALWAYS_EAGER=true` (no Redis); do not use that for real device integration.

---

## 7. Connecting Zone B (Flutter)

- **REST sync** — `POST /v1/sync/push`, `GET /v1/sync/pull` with headers `X-Gateway-Id` and `X-Sync-Batch-Id` as documented in [api-endpoints.md](api-endpoints.md) and `API_SPEC.md`.
- **gRPC** — Ensure `GRPC_PORT=50051` (or your chosen port). Use the proto in `protos/sync.proto`; send metadata **`x-client-version`** (semver) ≥ `GRPC_MIN_CLIENT_VERSION`. The server uses an **insecure** port in dev (`grpc.aio`); use TLS termination in production (reverse proxy or mutual TLS as you design).
- **Base URL** — Point the app at `http://<host>:8000` (or HTTPS behind a proxy). Emulator note: Android emulator often uses `10.0.2.2` to reach the host loopback.

---

## 8. Connecting the React dashboard

The repo includes a **Vite + React** app under **`dashboard/`** (shadcn/ui, Bangladesh-inspired theme). From that folder: `npm install`, copy **`dashboard/.env.example`** to **`.env.local`**, then `npm run dev` (default port **5173**).

- **CORS** — `app/main.py` allows broad origins in development (`allow_origins=["*"]`). Tighten for production.
- **Analytics** — Set `DASHBOARD_ADMIN_KEY` in `.env`, restart the API, and send the same value in header **`X-Dashboard-Admin-Key`** on `GET /v1/analytics/map-layers` and `GET /v1/analytics/sos-queue`.
- **Field devices / recent activity** — Set `REPORTS_DEV_KEY` in the API `.env`. In the React app (for example `.env.local`), set **`VITE_DEV_REPORTS_KEY`** to the **same** string so the UI can call `GET /reports` (includes `source_gateway_id` per row).
- **Sync history** — Set **`SYNC_ADMIN_KEY`** on the API and **`VITE_SYNC_ADMIN_KEY`** in the React app to the same value for `GET /v1/sync/conflicts` (sync batches / status).
- **Demo data** — Run `python scripts/seed_dashboard_demo.py` after the API is up; it posts several batches so multiple gateways and sync log rows appear when the keys above are set.
- **Dev server** — Typical React port `3000` works with the current CORS settings.

Example React `.env.local` (values must match the API `.env`):

```text
VITE_API_URL=http://127.0.0.1:8000
VITE_DASHBOARD_ADMIN_KEY=local-dev-dashboard-key
VITE_DEV_REPORTS_KEY=local-dev-reports-key
VITE_SYNC_ADMIN_KEY=local-dev-sync-admin-key
```

---

## 9. Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `password authentication failed for user "jibon"` | `DATABASE_URL` port (**5433** vs local 5432), or wrong DB. See README “Still seeing password authentication failed…”. |
| Flutter cannot reach API | Firewall, `--host 0.0.0.0`, correct LAN IP (not `127.0.0.1` from a phone). |
| `404` on `/v1/sync/*` | Use **`/v1/`** prefix; unversioned `/sync/*` is not mounted. |
| Analytics `404` | `DASHBOARD_ADMIN_KEY` unset (analytics disabled by design). |
| Field devices / activity empty | `REPORTS_DEV_KEY` unset on API, or React `VITE_DEV_REPORTS_KEY` mismatch; restart API after `.env` changes. |
| Sync history “admin key not configured” | `SYNC_ADMIN_KEY` unset on API, or `VITE_SYNC_ADMIN_KEY` mismatch in the React app. |
| gRPC connection refused | `GRPC_PORT` not `0`; port 50051 not blocked; client targets correct host/port. |

---

## 10. Load testing (k6)

Install [k6](https://k6.io/docs/get-started/installation/) (`winget install GrafanaLabs.k6` on Windows). If `k6` is not found, **restart the terminal** so `PATH` updates, or run **`.\scripts\k6.ps1`** from the repo root (see **`k6/README.md`**).

With the API running:

```bash
k6 run k6/health.js
k6 run k6/sync-push.js
k6 run -e DASHBOARD_ADMIN_KEY=<your-key> k6/analytics.js
```

See **`k6/README.md`** for `BASE_URL`, rate-limit notes, and CI export options.

---

## Quick reference

```text
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
celery -A app.worker worker -l info   # optional second terminal
```

Further detail: `README.md`, `API_SPEC.md`, `SECURITY_MODEL.md`.
