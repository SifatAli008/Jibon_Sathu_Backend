# Cloud API contract (Issues #1–#13)

Base URL: deployment-specific. Local default: `http://127.0.0.1:8000`.

All JSON bodies use UTF-8. Timestamps are ISO 8601 with timezone (RFC 3339), preferably UTC with `Z` suffix.

## API versioning (Issue #10)

All **sync** and **model** HTTP routes live under **`/v1/`** (frozen contract for delay-tolerant gateways). Requests to legacy unversioned paths (for example `POST /sync/push`) return **404 Not Found**. **`GET /health`** and dev-only **`GET /reports`** remain at the **root** (no `/v1` prefix).

---

## `GET /health`

**Purpose:** Liveness and cheap database connectivity check. Does **not** run migrations.

### Response

**200 OK**

```json
{
  "status": "ok",
  "db": "ok"
}
```

**503 Service Unavailable** — database ping failed

```json
{
  "status": "error",
  "db": "error"
}
```

---

## `GET /reports` (dev only)

**Purpose:** Minimal read-back for integration tests and Issue #4 spikes. **Disabled** unless `REPORTS_DEV_KEY` is set in the server environment.

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-Dev-Reports-Key` | yes | Must equal `REPORTS_DEV_KEY`. |

### Response

**200 OK** — JSON array of reports (most recently `updated_at` first), capped by `limit` (default 200, max 500).

**404 Not Found** — `REPORTS_DEV_KEY` is unset (endpoint treated as absent).

**401 Unauthorized** — header missing or wrong.

---

## `POST /v1/sync/push`

**Purpose:** Batch ingest with **Issue #2 merge policy** inside one database transaction: idempotent batches, deterministic road/supply merge, append-only SOS, strict validation.

### Merge summary

| `kind` | Behavior |
|--------|----------|
| `road`, `supply` | If `segment_key` is set: one canonical row per `(kind, segment_key)`; **latest `updated_at` wins**. Winner **replaces** `status`, `payload`, `created_at`, `updated_at`, `deleted_at`, `source_gateway_id` on the **survivor row’s primary key** (first writer’s `id` may remain while later gateways send different report `id`s). If `segment_key` is absent: same last-write-wins rules keyed by existing row `id`. |
| `sos` | **Append-only:** first successful insert for an `id` wins; later pushes with the same `id` are **no-ops** (payload not updated). SOS rows are **not** `UPDATE`d or `DELETE`d on push. `deleted_at` from the client is ignored for SOS inserts. |

**Tie-break** (same `updated_at` on incoming vs existing row): lexicographic compare `(str(source_gateway_id), str(report_id))` — **larger** tuple wins so outcomes are stable.

**Strict batch (Issue #2):** If **any** report fails validation (clock skew, id/kind conflict, batch size), the **entire** batch fails with **422** and **nothing** from that request is committed (including `sync_logs`).

**Batch size:** At most `MAX_SYNC_BATCH_ITEMS` reports per request (default **500**). Oversized batches return **413**.

**Issue #5 tombstones:** Deletes are represented as **CRDT tombstone rows** (`is_tombstone=true`, usually with `deleted_at`). The server **never hard-deletes** mergeable `road` / `supply` rows on push. Once a canonical row is tombstoned, **non-tombstone pushes cannot resurrect it**, even if their wall-clock `updated_at` is newer (prevents “zombie” replay from stale gateways).

**Server ordering:** Each accepted row mutation receives a monotonic `server_sequence_id` allocated from a single Postgres sequence (`server_sequence_global`). This is the safe ordering signal for pull/merge; **do not rely on `updated_at` alone** across zones.

### Headers (required)

| Header | Type | Description |
|--------|------|-------------|
| `X-Gateway-Id` | UUID | Must equal `gateway_id` in the JSON body. |
| `X-Sync-Batch-Id` | UUID | Must equal `batch_id` in the JSON body. Client-generated idempotency key. |
| `Authorization` | string | When `REQUIRE_GATEWAY_AUTH=true`: **`Authorization: Bearer <gateway-secret>`** (Issue #7). |

### Request body

```json
{
  "gateway_id": "550e8400-e29b-41d4-a716-446655440000",
  "batch_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "gateway_name": "gw-north-1",
  "reports": [
    {
      "id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
      "kind": "road",
      "segment_key": "BD-DHK-12-450",
      "status": "damaged",
      "payload": { "notes": "pothole", "lat": 23.7, "lon": 90.4 },
      "created_at": "2026-04-12T10:00:00Z",
      "updated_at": "2026-04-12T10:05:00Z",
      "deleted_at": null
    }
  ]
}
```

| Field | Required | Notes |
|-------|----------|--------|
| `gateway_id` | yes | UUID; must match `X-Gateway-Id`. |
| `batch_id` | yes | UUID; must match `X-Sync-Batch-Id`. |
| `gateway_name` | no | If omitted, server uses `gateway-{first 8 of id}`. Upserts `gateways` row and refreshes `last_seen_at`. |
| `reports` | yes | Array (may be empty). Unknown JSON keys are rejected (`422`). |

**Report item**

| Field | Required | Notes |
|-------|----------|--------|
| `id` | yes | UUID. For SOS, stable id for idempotency. For road/supply with `segment_key`, may differ from the canonical row `id` after cross-gateway merge. |
| `kind` | yes | Closed set: `road`, `sos`, `supply`. |
| `segment_key` | no | For `road` / `supply`, preferred natural merge key when present. |
| `status` | no | Defaults to empty string. |
| `payload` | no | JSON object; defaults `{}`. |
| `created_at` | yes | `timestamptz` |
| `updated_at` | yes | `timestamptz` |
| `deleted_at` | no | For `road` / `supply`, applied when the incoming row wins; ignored for SOS. |
| `is_tombstone` | no | Explicit tombstone without `deleted_at` (optional). |

**Tombstone JSON example**

```json
{
  "id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
  "kind": "road",
  "segment_key": "BD-DHK-12-450",
  "status": "deleted",
  "payload": {},
  "created_at": "2026-04-12T10:00:00Z",
  "updated_at": "2026-04-12T10:05:00Z",
  "deleted_at": "2026-04-12T10:05:00Z",
  "is_tombstone": true
}
```

**Clock skew:** If **any** report has `created_at` or `updated_at` more than `MAX_FUTURE_SKEW_SECONDS` (default **300**) ahead of server UTC, the **whole batch** returns **422** (strict mode).

### Response

**200 OK**

```json
{
  "idempotent_replay": false,
  "record_count": 1,
  "applied_count": 1,
  "rejected": [],
  "sync_log_status": "applied"
}
```

| Field | Description |
|-------|-------------|
| `idempotent_replay` | `true` if this `(gateway_id, batch_id)` was already processed; no duplicate writes. |
| `record_count` | Number of report objects in the request body. |
| `applied_count` | Number of **rows inserted or updated** after merge (SOS duplicate / road loser → 0 touches for that item). |
| `rejected` | Reserved; always `[]` on **200** under strict validation. |
| `sync_log_status` | `applied` on success, or stored status on idempotent replay. |

### Error responses

| Code | When |
|------|------|
| `400 Bad Request` | `gateway_id` / `batch_id` disagree with headers. |
| `413 Payload Too Large` | Batch exceeds `MAX_SYNC_BATCH_ITEMS` (default **500**). |
| `422 Unprocessable Entity` | Pydantic validation, strict batch validation (clock skew, kind/id conflict), etc. |
| `429 Too Many Requests` | Rate limit exceeded on `/v1/sync/*` (Issue #8). Includes `Retry-After` (seconds). |
| `500 Internal Server Error` | Unexpected persistence or server faults (not part of the stable contract). |

---

## `GET /v1/sync/pull` (Issue #6)

**Purpose:** Downward sync for Gateways to catch up after offline periods.

### Query parameters

| Param | Default | Description |
|------|---------|-------------|
| `since_sequence_id` | `0` | Return rows with `server_sequence_id` **greater than** this value (cursor). |
| `limit` | `100` | Page size (1–500). |

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-Gateway-Id` | yes | Gateway identity (must match provisioned gateway when auth is enabled). |
| `Authorization` | if enabled | `Bearer` token when `REQUIRE_GATEWAY_AUTH=true`. |

### Response (200)

```json
{
  "items": [
    {
      "id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
      "kind": "road",
      "segment_key": "BD-DHK-12-450",
      "status": "deleted",
      "payload": {},
      "created_at": "2026-04-12T10:00:00+00:00",
      "updated_at": "2026-04-12T10:05:00+00:00",
      "deleted_at": "2026-04-12T10:05:00+00:00",
      "source_gateway_id": "550e8400-e29b-41d4-a716-446655440000",
      "server_sequence_id": 42,
      "is_tombstone": true
    }
  ],
  "max_sequence_id": 42,
  "has_more": false,
  "latest_model_version": {
    "name": "road_decay_model",
    "version": "2026.04.12-1",
    "sha256": "…",
    "size_bytes": 1234,
    "min_gateway_version": "1.0.0",
    "input_schema_hash": null
  }
}
```

**Pagination / cursor:** Gateways should store `max_sequence_id` from the last successful pull and pass `since_sequence_id=<that value>` on the next pull. If `has_more` is `true`, re-request with the updated cursor (same `since_sequence_id` until empty).

---

## `GET /v1/sync/conflicts` (Issue #8)

**Purpose:** Auditability for merge decisions (noop tombstone blocks, LWW losers, etc.).

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-Sync-Admin-Key` | yes (when enabled) | Must match `SYNC_ADMIN_KEY`. If unset, endpoint returns **404** (disabled). |

### Query parameters

| Param | Default | Description |
|------|---------|-------------|
| `since_id` | `0` | Return `sync_logs.id` rows greater than this value. |
| `limit` | `50` | Page size (1–200). |

### Response (200)

Returns `sync_logs` rows including `merge_audit` JSON (when present) describing per-report outcomes for that batch.

---

## ONNX models (Issues #3, #9)

Artifacts are tracked in Postgres (`model_artifacts`) and stored on disk under `MODEL_ARTIFACTS_BASE_DIR` (default `artifacts/models`).

**Issue #9 compatibility:** Each artifact records **`min_gateway_version`** (required semver string for Zone B app builds) and optional **`input_schema_hash`** (stable fingerprint of ONNX input / feature contract). Gateways should refuse downloads when their app version is lower than `min_gateway_version`.

### `GET /v1/models/{name}/latest`

Returns metadata for the row where `is_latest` is true for `name` (URL-safe: letters, digits, `_`, `.`, `-`).

JSON fields include: `name`, `version`, `sha256`, `size_bytes`, `updated_at`, **`min_gateway_version`**, **`input_schema_hash`** (nullable).

When `REQUIRE_GATEWAY_AUTH=true`, requires **`X-Gateway-Id`** and **`Authorization: Bearer <secret>`** (Issue #7).

**404** if nothing published.

### `GET /v1/models/{name}/latest/file`

Returns the `.onnx` bytes as `application/octet-stream`, `Content-Disposition: attachment`, and **`ETag: "<sha256>"`** (Starlette `FileResponse` / sendfile; suitable for large files without loading the whole model into memory).

**304 Not Modified** if request header `If-None-Match` matches the artifact SHA256 (case-insensitive).

**401** when `MODELS_DOWNLOAD_KEY` is set and `X-Model-Download-Key` is missing or wrong, or when gateway auth is enabled and gateway headers/token are invalid.

### `POST /v1/models/{name}/publish`

**404** when `MODELS_ADMIN_KEY` is unset (publishing disabled). Otherwise requires header **`X-Models-Admin-Key`** matching `MODELS_ADMIN_KEY`.

Multipart form fields:

| Field | Required | Description |
|-------|----------|-------------|
| `version` | yes | Model version string. |
| `min_gateway_version` | yes | Minimum Zone B gateway **app** version (semver). Omitting it yields **422**. |
| `input_schema_hash` | no | Optional stable hash of input schema / ONNX IO contract. |
| `file` | yes | Binary `.onnx` payload. |

Promotes the upload as the sole latest row for `name` in one transaction (other versions for that name get `is_latest=false`). Max upload **50 MiB**.

**201** returns the same JSON shape as `GET .../latest`.

**409** on duplicate `(name, version)` or other integrity violations.

### Retrain / redeploy workflow

1. `python scripts/export_road_decay_onnx.py --output-dir artifacts/models` (JSON includes suggested `min_gateway_version`, e.g. `1.0.0`).
2. `alembic upgrade head` (if schema changed)
3. `python scripts/publish_model.py road_decay_model --version <new> --min-gateway-version 1.0.0 --file artifacts/models/road_decay_model.onnx`  
   or `POST /v1/models/road_decay_model/publish` with admin key and form fields above.
4. Gateways call `GET /v1/models/road_decay_model/latest`, compare `sha256` and **`min_gateway_version`** against the local app, then conditionally `GET .../latest/file` and verify the file hash matches metadata.

### Tests (ML metadata)

With Postgres running and migrations applied:

```bash
pytest tests/test_models_onnx.py -q
```

---

## Dashboard analytics (Issue #13)

**Purpose:** Read-heavy JSON for the React dashboard (map layers, SOS queue). Same merge and sync rules as **`POST /v1/sync/push`** apply to ingest; analytics are **read-only** aggregates.

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-Dashboard-Admin-Key` | yes (when enabled) | Must match `DASHBOARD_ADMIN_KEY`. If unset, routes return **404** (disabled). |

### `GET /v1/analytics/map-layers`

Returns a **GeoJSON-like** `FeatureCollection` (see `app/services/analytics_service.py`): points for non-tombstone `road` / `supply` rows that include `lat` / `lon` in `payload`, ordered by `server_sequence_id` (capped server-side).

### `GET /v1/analytics/sos-queue`

Returns a JSON array of open SOS-style rows, ordered by `priority_score` then `server_sequence_id`.

---

## gRPC `SyncIngest` (Issue #12)

**Purpose:** Same batch ingest semantics as **`POST /v1/sync/push`** via **`jibon.sync.v1.SyncIngest/PushBatch`** (see `protos/sync.proto`). Uses **`MergeService.apply_batch`** with `gateway_id` and `batch_id` from the protobuf request.

### Metadata

| Key | Required | Description |
|-----|----------|-------------|
| `x-client-version` or `x-gateway-version` | yes | Semver string; must be **≥** `GRPC_MIN_CLIENT_VERSION` (default `1.0.0`). |

**FAILED_PRECONDITION** when the version is missing or too low.

---

## Idempotency

`sync_logs` has a unique constraint on `(gateway_id, batch_id)`. Retrying the **same** batch to **`POST /v1/sync/push`** returns **200** with `idempotent_replay: true` and the **stored** `record_count` / `applied_count` / `sync_log_status` without re-applying reports.

---

## Contract pinning

Zone B gateways should pin to **`/v1/`** paths and this document revision. Future incompatible changes should ship under `/v2/` (not yet defined) while keeping `/v1/` stable for offline nodes.
