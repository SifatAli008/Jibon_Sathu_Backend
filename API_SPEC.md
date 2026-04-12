# Cloud API contract (Issues #1–#2)

Base URL: deployment-specific. Local default: `http://127.0.0.1:8000`.

All JSON bodies use UTF-8. Timestamps are ISO 8601 with timezone (RFC 3339), preferably UTC with `Z` suffix.

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

## `POST /sync/push`

**Purpose:** Batch ingest with **Issue #2 merge policy** inside one database transaction: idempotent batches, deterministic road/supply merge, append-only SOS, strict validation.

### Merge summary

| `kind` | Behavior |
|--------|----------|
| `road`, `supply` | If `segment_key` is set: one canonical row per `(kind, segment_key)`; **latest `updated_at` wins**. Winner **replaces** `status`, `payload`, `created_at`, `updated_at`, `deleted_at`, `source_gateway_id` on the **survivor row’s primary key** (first writer’s `id` may remain while later gateways send different report `id`s). If `segment_key` is absent: same last-write-wins rules keyed by existing row `id`. |
| `sos` | **Append-only:** first successful insert for an `id` wins; later pushes with the same `id` are **no-ops** (payload not updated). SOS rows are **not** `UPDATE`d or `DELETE`d on push. `deleted_at` from the client is ignored for SOS inserts. |

**Tie-break** (same `updated_at` on incoming vs existing row): lexicographic compare `(str(source_gateway_id), str(report_id))` — **larger** tuple wins so outcomes are stable.

**Strict batch (Issue #2):** If **any** report fails validation (clock skew, id/kind conflict, batch size), the **entire** batch fails with **422** and **nothing** from that request is committed (including `sync_logs`).

**Batch size:** At most `MAX_SYNC_BATCH_ITEMS` reports per request (default **10000**).

### Headers (required)

| Header | Type | Description |
|--------|------|-------------|
| `X-Gateway-Id` | UUID | Must equal `gateway_id` in the JSON body. |
| `X-Sync-Batch-Id` | UUID | Must equal `batch_id` in the JSON body. Client-generated idempotency key. |

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
| `422 Unprocessable Entity` | Pydantic validation, strict batch validation (clock skew, kind/id conflict, batch too large), etc. |
| `500 Internal Server Error` | Unexpected persistence or server faults (not part of the stable contract). |

---

## Idempotency

`sync_logs` has a unique constraint on `(gateway_id, batch_id)`. Retrying the **same** batch returns **200** with `idempotent_replay: true` and the **stored** `record_count` / `applied_count` / `sync_log_status` without re-applying reports.

---

## Versioning

Push lives under `/sync`. Global API version header or URL prefix may be introduced later; Zone B clients should pin to this document revision in their repository.
