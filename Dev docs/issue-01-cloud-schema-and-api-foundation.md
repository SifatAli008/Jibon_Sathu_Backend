# Issue #1 — Cloud Layer Schema and API Foundation

**Digital Delta · Zone A (Cloud)**  
**Status:** Specification and implementation guide (pre-code or alongside first sprint)  
**Depends on:** Nothing upstream.

---

## 1. Why this issue exists

Zone A is described as the only place where you can reasonably insist on stronger consistency. Field gateways work with partial connectivity; the cloud does not get that excuse in the architecture story. That means the first real engineering work is not “a FastAPI app,” it is a **contract**: what lives in Postgres, how objects are identified across zones, and how a gateway is allowed to talk to you in bulk.

If you skip this step, merge logic (Issue #2) and model distribution (Issue #3) will fight the schema instead of using it.

---

## 2. Scope (in / out)

**In scope**

- PostgreSQL as the system of record for global road marking state, SOS events, and supply-related records (exact supply fields can follow the same pattern as reports once product defines them).
- ORM layer (SQLAlchemy 2.x style or Tortoise — pick one team-wide; this doc stays neutral but assumes async-friendly access if you expect high concurrency).
- Alembic (or equivalent) migrations that apply cleanly on empty and upgraded databases.
- FastAPI application shell: configuration, DB session lifecycle, `GET /health` (or `/` returning health JSON), and `POST /sync/push` as a **stub or thin validation path** that persists enough to prove the pipeline (full merge in Issue #2).
- Pydantic request/response models with tests.
- Written API contract (`API_SPEC.md` at repo root or under `docs/` — team choice) and an ER diagram artifact (Mermaid in repo or exported PNG from your tool).

**Out of scope for Issue #1**

- Final conflict resolution (that is Issue #2).
- ONNX build and serve (Issue #3).
- Gateway simulation and chaos tests (Issue #4).

---

## 3. Design principles

1. **UUIDs everywhere that cross zone boundaries.** Gateways may generate IDs offline. The cloud should accept them as first-class keys where possible, so you are not re-keying rows on ingest (which breaks references and audit trails).
2. **Sync is batch-first.** HTTP overhead and intermittent links favor “send me everything you accumulated since cursor X” rather than chatty single-row APIs for the primary path.
3. **Everything traceable.** If something lands in the database, you should be able to answer: which gateway, which batch, when, and what idempotency key (if any) applied.

---

## 4. Entity model (draft)

### 4.1 Reports

Think of a **report** as the smallest unit a volunteer or sensor pipeline files about a road segment, SOS, or supply point. You may split into multiple tables later; for v1 a single `reports` table with a `kind` enum or string discriminator keeps migration noise down.

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID, PK | Client-generated preferred; server may generate only if client omitted and policy allows. |
| `kind` | enum / text | e.g. `road`, `sos`, `supply` |
| `payload` | JSONB | Flexible attributes (damage score, geo, notes). Structured columns can be extracted later. |
| `segment_key` | text nullable | Stable key for “same stretch of road” if you have one; used later for merge. |
| `status` | text | Workflow state for road-type reports. |
| `created_at` | timestamptz | First observation time from device if trusted; else server time. |
| `updated_at` | timestamptz | Last mutation time for merge comparisons. |
| `source_gateway_id` | UUID FK | Originating gateway (nullable only if server-created). |
| `deleted_at` | timestamptz nullable | Soft delete for non-SOS if you need it; SOS path may ignore deletes (Issue #2). |

Indexes you will almost certainly want: `(kind, segment_key)`, `(updated_at DESC)`, GIN on `payload` only if you query inside JSON heavily.

### 4.2 SyncLogs

Purpose: **audit and debugging**, not the primary dedupe mechanism (that should be idempotent batch keys + row-level rules).

| Column | Type | Notes |
|--------|------|--------|
| `id` | bigserial / UUID | Surrogate ok here. |
| `gateway_id` | UUID FK | Who pushed. |
| `batch_id` | UUID | Client-supplied batch identifier for idempotency. |
| `received_at` | timestamptz | Server wall clock. |
| `record_count` | int | Rows claimed in batch. |
| `applied_count` | int | Rows actually written after dedupe/merge. |
| `status` | text | `received`, `applied`, `failed`, `partial` — define enum in code. |
| `error_detail` | text nullable | Truncated message for operators. |

Unique constraint on `(gateway_id, batch_id)` so a duplicate POST does not double-apply.

### 4.3 Gateways (lookup)

Minimal table: `id`, `name`, `last_seen_at`, optional `public_key` or token reference if auth lands later.

---

## 5. API surface (Issue #1 level)

### Health

- `GET /health` → `{ "status": "ok", "db": "ok" }` and non-200 if DB ping fails.  
  Keep it cheap; do not run migrations here.

### Sync push (skeleton)

`POST /sync/push`

**Headers (recommended even if optional in v1)**

- `X-Gateway-Id`: UUID  
- `X-Sync-Batch-Id`: UUID (idempotency)

**Body (illustrative)**

```json
{
  "gateway_id": "uuid",
  "batch_id": "uuid",
  "reports": [
    {
      "id": "uuid",
      "kind": "road",
      "segment_key": "BD-DHK-12-450",
      "status": "damaged",
      "payload": { "notes": "...", "lat": 23.7, "lon": 90.4 },
      "created_at": "2026-04-12T10:00:00Z",
      "updated_at": "2026-04-12T10:05:00Z"
    }
  ]
}
```

Issue #1 acceptance: validate payload, open transaction, insert/update in a **defined but simple** way (e.g. upsert by `id` only), write `SyncLogs`, commit. Issue #2 replaces the naive upsert with merge policy.

Document the exact JSON in `API_SPEC.md` so Zone B implementers are not guessing.

---

## 6. Migrations and environments

- Local: Docker Compose with Postgres 15+ is enough for most teams.
- CI: spin Postgres service container, run `alembic upgrade head`, run pytest.
- Production: run migrations as a separate step before rolling new app pods; never rely on app startup to migrate unless you fully own the risks.

---

## 7. Testing (what “done” looks like)

**Pydantic / validation**

- Reject unknown `kind` if you use a closed set.
- Reject missing `batch_id` or `gateway_id` if those are required.
- Clock skew: decide whether future-dated `updated_at` is rejected or clamped; document the choice.

**Database**

- Connection test against real Postgres in CI.
- CRUD: create report, read back, update, list by gateway.

**API**

- Health returns 200 when DB is up.
- Push accepts a minimal valid batch and returns a structured response (e.g. counts, any rejected item ids).

---

## 8. Risks and open questions

- **Who generates report UUIDs?** If both gateway and server can create rows, document the rule to avoid collisions and orphan segments.
- **PII in SOS payloads:** JSONB is convenient; policy may require encryption at rest or field-level redaction later — does not block Issue #1 but affects indexing.
- **Supply data:** if it differs materially from `reports`, split table early to avoid a “god table” that every later feature fights.

---

## 9. Deliverables checklist

- [ ] FastAPI project layout (app package, settings, DB session).
- [ ] Models + Alembic migrations.
- [ ] `GET /health` wired to DB.
- [ ] `POST /sync/push` with validation + transactional write + `SyncLogs`.
- [ ] `API_SPEC.md` with request/response examples and error codes.
- [ ] ER diagram (Mermaid recommended: easy diff in Git).
- [ ] Pytest suite covering validation + DB smoke + one happy-path push.

---

## 10. Handoff to Issue #2

Leave the push handler structured so merge policy is a **pure function or service** that takes “existing row + incoming row” and returns “desired row,” plus a list of append-only SOS events. The skeleton you ship in Issue #1 should not scatter SQL across the route; one service module makes Issue #2 reviewable.
