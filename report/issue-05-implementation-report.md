# Implementation report — Issue #5 (Server sequence IDs + tombstones)

**Date:** 2026-04-12  
**Dependencies:** Issue #4 (gateway spike) recommended; schema builds on Issues #1–#3.

---

## Deliverables

| Item | Status | Location |
|------|--------|----------|
| Postgres sequence + `reports.server_sequence_id` | **Done** | `alembic/versions/20260412_0003_server_sequence_tombstones.py` |
| `reports.is_tombstone` + `deleted_at` semantics | **Done** | `app/models/report.py`, `app/schemas/sync.py` |
| `sync_logs.server_sequence_id` | **Done** | `app/models/sync_log.py`, migration `0003` |
| Merge respects tombstones (stale live cannot resurrect) | **Done** | `app/services/merge_policy.py`, `app/services/merge_service.py` |
| Sequence allocation only on successful mutation | **Done** | `app/services/server_sequence.py` |
| API documentation (tombstone payload) | **Done** | `API_SPEC.md` |
| Tests | **Done** | `tests/test_issues_5_8.py`, `tests/test_merge_policy.py` (existing suite still passes) |

---

## Behavior notes

- A single global sequence (`server_sequence_global`) allocates **unique** ids for both `reports` and `sync_logs`, preserving monotonic ordering across successful mutations.
- Tombstone precedence is implemented as: **if the canonical row is a tombstone, any non-tombstone incoming item is a no-op** (even if its `updated_at` is newer).

---

## Ops

Apply migrations:

```bash
alembic upgrade head
```

---

## Follow-ups

If you need “undelete” workflows, that requires an explicit product rule beyond Issue #5’s zombie-prevention semantics.
