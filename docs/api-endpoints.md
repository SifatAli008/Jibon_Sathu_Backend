# Zone A API — endpoint reference

Base URL (local): `http://127.0.0.1:8000` — replace with your host and scheme (`https://` behind a reverse proxy) in production.

All **sync** and **model** HTTP routes are under **`/v1/`**. **`GET /health`** and dev **`GET /reports`** are at the **root** (no `/v1` prefix).

For request/response bodies, validation rules, and merge semantics, see **`API_SPEC.md`** in the repo root.

---

## Root

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service name and link to OpenAPI docs. |
| `GET` | `/docs` | Swagger UI (interactive). |
| `GET` | `/openapi.json` | OpenAPI schema. |

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness and DB ping (`200` / `503`). |

---

## Sync (v1) — gateways & Flutter (REST)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/sync/push` | Batch ingest (merge policy, idempotent per `(gateway_id, batch_id)`). |
| `GET` | `/v1/sync/pull` | Downward sync cursor by `server_sequence_id`. |
| `GET` | `/v1/sync/conflicts` | Merge audit log (`sync_logs`). |

### `POST /v1/sync/push`

| Header | Required | Notes |
|--------|----------|--------|
| `X-Gateway-Id` | Yes | UUID; must match JSON `gateway_id`. |
| `X-Sync-Batch-Id` | Yes | UUID; must match JSON `batch_id`. |
| `Authorization` | If `REQUIRE_GATEWAY_AUTH=true` | `Bearer <gateway-secret>`. |

### `GET /v1/sync/pull`

| Header | Required | Notes |
|--------|----------|--------|
| `X-Gateway-Id` | Yes | |
| `Authorization` | If gateway auth enabled | Bearer token. |

Query: `since_sequence_id` (default `0`), `limit` (1–500).

### `GET /v1/sync/conflicts`

| Header | Required | Notes |
|--------|----------|--------|
| `X-Sync-Admin-Key` | When enabled | Must match `SYNC_ADMIN_KEY`. If unset, route is disabled (`404`). |

Query: `since_id`, `limit`.

---

## Models (v1) — ONNX distribution

`{name}` is URL-safe (letters, digits, `_`, `.`, `-`).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/models/{name}/latest` | Latest metadata (version, `sha256`, `min_gateway_version`, etc.). |
| `GET` | `/v1/models/{name}/latest/file` | Binary `.onnx` (`ETag` = SHA256). |
| `POST` | `/v1/models/{name}/publish` | Multipart publish (admin); disabled if `MODELS_ADMIN_KEY` unset. |

### Common headers (models)

| Header | When |
|--------|------|
| `X-Gateway-Id` + `Authorization` | If `REQUIRE_GATEWAY_AUTH=true` (see `require_gateway_for_models`). |
| `X-Model-Download-Key` | If `MODELS_DOWNLOAD_KEY` is set — **file** download only. |
| `X-Models-Admin-Key` | `POST .../publish` when `MODELS_ADMIN_KEY` is set. |

---

## Analytics (v1) — React dashboard

Disabled until `DASHBOARD_ADMIN_KEY` is set in the environment (`404` when disabled).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/analytics/map-layers` | GeoJSON-style map features (road/supply with `lat`/`lon` in payload). |
| `GET` | `/v1/analytics/sos-queue` | Prioritized SOS-style items JSON. |

| Header | Required |
|--------|----------|
| `X-Dashboard-Admin-Key` | Yes — must match `DASHBOARD_ADMIN_KEY`. |

Optional: responses may be cached when Redis (`CELERY_BROKER_URL`) is configured; see `ANALYTICS_CACHE_TTL_SECONDS`.

---

## Reports (dev only)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/reports` | Raw read-back for debugging. **404** if `REPORTS_DEV_KEY` unset. |

| Header | Required |
|--------|----------|
| `X-Dev-Reports-Key` | Must match `REPORTS_DEV_KEY`. |

---

## gRPC (Flutter / high-throughput ingest)

Not an HTTP path: separate TCP port (default **`50051`** when `GRPC_PORT` is not `0`).

| Service | RPC | Package / proto |
|---------|-----|-----------------|
| `SyncIngest` | `PushBatch` | `protos/sync.proto` → package `jibon.sync.v1` |

**Metadata (required for version gate):**

| Key | Meaning |
|-----|---------|
| `x-client-version` or `x-gateway-version` | Semver string; must be ≥ `GRPC_MIN_CLIENT_VERSION` (default `1.0.0`). |

Semantics match **`POST /v1/sync/push`** (same `MergeService` rules). Regenerate stubs: `python scripts/gen_grpc_stubs.py`.

---

## Related documents

| Document | Contents |
|----------|----------|
| `API_SPEC.md` | Full contract: merge rules, errors, tombstones, models. |
| `SECURITY_MODEL.md` | Gateway provisioning, bearer auth, dashboard key. |
| `README.md` | ONNX publish, gateway sim, disaster backoff. |
| `docs/startup-guide.md` | How to run Postgres, API, Celery, and clients locally. |
