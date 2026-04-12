# Implementation report — Issue #2 (Server-side delta merge logic)

**Reference:** [Dev docs/issue-02-server-side-delta-merge-logic.md](../Dev%20docs/issue-02-server-side-delta-merge-logic.md)  
**Date:** 2026-04-12  
**Depends on:** Issue #1 (schema, `sync_logs`, push shell).

---

## 1. Deliverables checklist (Issue §8)

| Deliverable | Status | Where |
|-------------|--------|--------|
| Merge policy behind `POST /sync/push` | **Done** | `app/services/merge_service.py` (`MergeService.apply_batch`), `app/services/merge_policy.py` (pure rules) |
| `SyncLogs` for every merge | **Done** | Success path only: one `applied` row per successful batch; strict failures do **not** commit a success log (batch rolls back) |
| Tests: conflict, SOS idempotency, rollback, replay | **Done** | `tests/test_merge_policy.py`, `tests/test_api.py` (async `httpx` client) |
| Inline comments on invariants / tie-breakers | **Done** | Module docstrings and comments in `merge_policy.py` / `merge_service.py` |

---

## 2. Rules implemented

| Area | Behavior |
|------|----------|
| **Road / supply** | With `segment_key`: canonical row per `(kind, segment_key)`; latest `updated_at` wins; tie → lexicographic `(source_gateway_id, report id)` as strings; winner **updates the survivor PK** (payload/status full replace). Without `segment_key`: same LWW keyed by existing row `id`. |
| **SOS** | Append-only: `INSERT`; duplicate `id` → **no-op** (first write immutable). No `UPDATE`/`DELETE` on push. `deleted_at` ignored on insert. |
| **Strict batch** | Any clock skew, batch size over limit, or cross-kind `id` conflict → **422**, **no** partial writes, **no** success `sync_logs` row. |
| **Idempotent replay** | Unchanged: existing `(gateway_id, batch_id)` in `sync_logs` short-circuits. |
| **`applied_count`** | Counts DB **insert + update** operations; SOS duplicate / road loser → 0 for that item. |

---

## 3. Issue #4 handoff (Issue §9)

- **`GET /reports`**: enabled only when `REPORTS_DEV_KEY` is set; requires matching `X-Dev-Reports-Key`. Returns recent rows for integration / spike verification (not a production contract).

---

## 4. Testing notes

- Integration tests require Postgres (same as Issue #1).
- `SimulatedMergeFault` (after *N* successful touches) asserts rollback + **500** response; no rows for that batch’s segment keys remain after failure.

---

## 5. Operational / known limits (Issue §7)

- Ordering still trusts gateway-supplied `updated_at` (same as Issue #1 clock window); mitigations like `ingested_at` ordering are not in schema yet.
- Multiple historical rows per `segment_key` from older behavior are not compacted automatically; canonical selection uses `ORDER BY updated_at DESC, gateway_id::text, id::text`.

This report reflects the repository state when Issue #2 was implemented.
