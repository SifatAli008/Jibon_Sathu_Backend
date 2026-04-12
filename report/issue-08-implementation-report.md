# Implementation report — Issue #8 (Rate limits, payload caps, conflict observability)

**Date:** 2026-04-12  
**Dependencies:** Issue #7 (auth hooks) + Issue #5 merge audit storage.

---

## Deliverables

| Item | Status | Location |
|------|--------|----------|
| Per-gateway `/sync/*` rate limiting | **Done** | `slowapi` + `app/limits.py` + `app/main.py` |
| `429` + `Retry-After` | **Done** | `app/main.py` (`RateLimitExceeded` handler) |
| Max batch size default **500** + **413** | **Done** | `app/config.py`, `app/services/merge_service.py`, `app/api/routes/sync.py` |
| `sync_logs.merge_audit` JSON | **Done** | migration `0004`, `MergeService` |
| `GET /sync/conflicts` | **Done** | `app/api/routes/sync.py` |
| Documentation (`API_SPEC.md`, README downgrade) | **Done** | `API_SPEC.md`, `README.md` |
| Tests | **Done** | `tests/test_issues_5_8.py` |

---

## Configuration

- `SYNC_RATE_LIMIT` maps to `Settings.sync_rate_limit` (default `120/minute`).
- `SYNC_ADMIN_KEY` enables `GET /sync/conflicts` (returns **404** when unset).

---

## Load testing note

The repo includes targeted integration tests (auth, 413, conflicts). A full “100 concurrent clients → 429” load test is environment-dependent; use a staging runner with realistic network settings if you need sustained verification.
