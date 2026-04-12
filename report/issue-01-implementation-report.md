# Implementation report — Issue #1 (Cloud schema and API foundation)

**Reference:** [Dev docs/issue-01-cloud-schema-and-api-foundation.md](../Dev%20docs/issue-01-cloud-schema-and-api-foundation.md)  
**Date:** 2026-04-12  
**Outcome:** Implemented as specified for Issue #1 (naive upsert by report `id`, batch idempotency via `sync_logs`, traceable batches). Merge policy remains explicitly deferred to Issue #2.

---

## 1. Deliverables checklist (from Issue §9)

| Deliverable | Status | Notes |
|-------------|--------|--------|
| FastAPI project layout (app package, settings, DB session) | **Done** | `app/main.py`, `app/config.py`, `app/db.py` |
| Models + Alembic migrations | **Done** | SQLAlchemy 2.x async models; revision `20260412_0001` |
| `GET /health` wired to DB | **Done** | Ping via `SELECT 1`; `503` if DB unreachable |
| `POST /sync/push` with validation + transactional write + `SyncLogs` | **Done** | Orchestration in `app/services/sync_push.py`; route in `app/api/routes/sync.py` |
| `API_SPEC.md` with request/response examples and error codes | **Done** | Repository root |
| ER diagram (Mermaid) | **Done** | [docs/er-diagram.md](../docs/er-diagram.md) |
| Pytest suite (validation + DB smoke + happy-path push) | **Done** | `tests/test_schemas.py`, `tests/test_api.py`; DB tests marked `@pytest.mark.integration` and auto-skipped when Postgres is not reachable at `DATABASE_URL` |

---

## 2. Design decisions mapped to the issue

| Issue principle | How it was implemented |
|-----------------|-------------------------|
| UUIDs across zones | `reports.id`, `gateways.id`, header/body `gateway_id` / `batch_id` as UUID |
| Batch-first sync | Single `POST /sync/push` with `reports[]` |
| Traceability | `sync_logs` records `gateway_id`, `batch_id`, counts, `status`, optional `error_detail`; gateway `last_seen_at` updated on push |
| Simple upsert (Issue #1) | PostgreSQL `INSERT … ON CONFLICT (id) DO UPDATE` on `reports` |
| Idempotent batches | Unique `(gateway_id, batch_id)` on `sync_logs`; replay returns `idempotent_replay: true` without re-writing reports |
| Clock skew | **Reject** individual reports when `created_at` or `updated_at` is more than `MAX_FUTURE_SKEW_SECONDS` (default **300**) ahead of server UTC; batch may be `partial` |

---

## 3. Handoff to Issue #2 (Issue §10)

- Ingest logic lives in **`app/services/sync_push.py`**, not scattered in the route handler, so merge policy can become a dedicated function or service consuming **existing row + incoming row** without rewriting the HTTP layer.
- Current behavior is intentionally a **full replace** on conflict for the stored columns (naive upsert). SOS append-only semantics and segment merge rules are **not** implemented here, per Issue #1 scope.

---

## 4. How to run locally

1. `docker compose up -d` (Postgres 16)
2. `pip install -e ".[dev]"`
3. `alembic upgrade head`
4. `uvicorn app.main:app --reload`

**CI:** `.github/workflows/ci.yml` runs `alembic upgrade head` and `pytest` against a Postgres service container.

---

## 5. Verification on this workspace

- `pytest` was executed successfully with **6 passed, 2 skipped** when Postgres was not available; the two skipped tests are the `@pytest.mark.integration` cases that require a live database at `DATABASE_URL`.
- With Postgres up and migrations applied, expect **8 passed, 0 skipped**.

---

## 6. Files added or central to this issue

| Area | Paths |
|------|--------|
| Application | `app/main.py`, `app/config.py`, `app/db.py`, `app/api/routes/*.py`, `app/models/*.py`, `app/schemas/*.py`, `app/services/sync_push.py` |
| Migrations | `alembic.ini`, `alembic/env.py`, `alembic/versions/20260412_0001_initial_schema.py` |
| Contract / diagrams | `API_SPEC.md`, `docs/er-diagram.md` |
| Tooling | `pyproject.toml`, `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`, `tests/*`, `README.md` |

---

## 7. Residual risks (from Issue §8, status after Issue #1)

- **Dual UUID producers:** Policy documented in `API_SPEC.md`: clients should send stable report UUIDs; server upserts on `id` only.
- **PII in SOS JSONB:** Not addressed in storage layer; noted for later policy.
- **Concurrent duplicate batch POST:** Extremely rare race on unique `sync_logs` could surface as `500`; acceptable for Issue #1; can be upgraded to “catch `IntegrityError` and treat as replay” in a follow-up.

This report closes the implementation tracking for Issue #1 at the repository state where this file was authored.
