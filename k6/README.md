# k6 load tests

Scripts target the Jibon Sathu FastAPI service. Install [k6](https://k6.io/docs/get-started/installation/) (Windows: `winget install GrafanaLabs.k6`).

### Windows: `k6` not recognized

The installer usually puts the binary at **`C:\Program Files\k6\k6.exe`**, but your **PATH** may not refresh until you **close and reopen** the terminal.

**Option A — new terminal** — Quit PowerShell/CMD and open it again, then `k6 version`.

**Option B — this session only:**

```powershell
$env:Path += ";C:\Program Files\k6"
k6 version
```

**Option C — wrapper (no PATH change):** from the **repo root**:

```powershell
.\scripts\k6.ps1 run k6/health.js
```

## Environment

| Variable | Scripts | Meaning |
|----------|---------|---------|
| `BASE_URL` | all | API root (default `http://127.0.0.1:8000`) |
| `GATEWAY_SECRET` | `sync-push.js` | Bearer token when `REQUIRE_GATEWAY_AUTH=true` (gateway must be provisioned) |
| `DASHBOARD_ADMIN_KEY` | `analytics.js` | Must match API `DASHBOARD_ADMIN_KEY` |

Pass with `-e`, for example:

```bash
k6 run -e BASE_URL=http://127.0.0.1:8000 k6/health.js
```

## Scripts

| File | What it exercises |
|------|-------------------|
| `health.js` | `GET /health` (liveness + DB ping) — good baseline |
| `sync-push.js` | `POST /v1/sync/push` with **empty** batches; **new UUIDs per iteration** so each request is a distinct gateway/batch (avoids hitting the per–`X-Gateway-Id` rate limit) |
| `analytics.js` | `GET /v1/analytics/map-layers` and `GET /v1/analytics/sos-queue` |

## Rate limits

Sync routes use `SYNC_RATE_LIMIT` (default `120/minute`) **per** `X-Gateway-Id`. The sync script uses a **unique** gateway ID each time; if you change it to reuse one gateway, lower VUs or raise the limit in the API `.env` for the test.

## Examples

```bash
# From repo root, API running on port 8000
k6 run k6/health.js
k6 run k6/sync-push.js
k6 run -e DASHBOARD_ADMIN_KEY=local-dev-dashboard-key k6/analytics.js
```

## CI

Use `k6 run --quiet --summary-export=summary.json k6/health.js` and archive `summary.json`, or Grafana Cloud k6.
