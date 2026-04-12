# Cloud API contract (Issue #1)

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

## `POST /sync/push`

**Purpose:** Batch ingest of `reports` from a field gateway. Issue #1 behavior: validate payload, transactional upsert **by report `id`**, append `sync_logs` row, enforce idempotency on `(gateway_id, batch_id)`.

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
| `id` | yes | UUID. Primary upsert key in Issue #1. |
| `kind` | yes | Closed set: `road`, `sos`, `supply`. |
| `segment_key` | no | Text, merge hint for Issue #2. |
| `status` | no | Defaults to empty string. |
| `payload` | no | JSON object; defaults `{}`. |
| `created_at` | yes | `timestamptz` |
| `updated_at` | yes | `timestamptz` |
| `deleted_at` | no | Soft delete timestamp when set. |

**Clock skew:** If `created_at` or `updated_at` is more than `MAX_FUTURE_SKEW_SECONDS` (default **300**) ahead of the server UTC clock, that report is **rejected** for the batch (not written). Other valid rows in the same batch are still applied; the batch `sync_logs.status` becomes `partial` when any row is rejected.

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
| `record_count` | Number of report objects in the request body (including rejected). |
| `applied_count` | Rows successfully upserted in this response (0 on idempotent replay of a prior success). |
| `rejected` | List of `{ "id": "<uuid string>", "reason": "<message>" }` for clock-skew rejects. |
| `sync_log_status` | `applied`, `partial`, or replayed status from stored `sync_logs` row. |

### Error responses

| Code | When |
|------|------|
| `400 Bad Request` | `gateway_id` / `batch_id` disagree with headers. |
| `422 Unprocessable Entity` | Pydantic validation (unknown `kind`, malformed UUID/timestamp, extra keys, etc.). |
| `500 Internal Server Error` | Unexpected persistence or server faults (not part of the stable contract). |

---

## Idempotency

`sync_logs` has a unique constraint on `(gateway_id, batch_id)`. Retrying the **same** batch returns **200** with `idempotent_replay: true` and the **stored** `record_count` / `applied_count` / `sync_log_status` without re-applying reports.

---

## Versioning

Issue #1 ships under path prefix `/sync` for push. Global API version header or URL prefix may be introduced later; Zone B clients should pin to this document revision in their repository.
