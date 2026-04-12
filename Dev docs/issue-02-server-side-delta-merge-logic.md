# Issue #2 — Server-Side Delta Merge Logic

**Digital Delta · Zone A (Cloud)**  
**Prerequisite:** Issue #1 (schema, push endpoint, `SyncLogs`, UUID strategy).  
**Problem statement:** Gateways accumulate changes offline. When connectivity returns, several gateways may report different truths about the same road segment, or duplicate the same SOS because retries and human urgency stack up. The cloud must merge without silently dropping volunteer work.

---

## 1. What “merge” means here

This is not a distributed CRDT exercise unless you choose that path later. For the product described, merge is **deterministic server policy** applied inside a database transaction:

1. Accept a batch from gateway G with idempotency key B.
2. If (G, B) already succeeded, short-circuit with the same outcome (idempotent replay).
3. For each incoming record, classify by `kind` and natural key (`id` and/or `segment_key` depending on type).
4. Apply rules, write rows, append audit.
5. Commit or roll back the **whole batch** (see failure scenario below).

---

## 2. Business rules (baseline proposal)

These should be reviewed with domain leads; the doc captures a sensible default for implementation and tests.

### 2.1 Road (and similar mutable) reports

- **Identity:** Primary merge key is `segment_key` if present and stable; otherwise fall back to `id` if the same segment always shares one UUID across gateways (only true if you coordinate ID issuance — often false). Prefer **explicit segment_key** from the field app where possible.
- **Conflict:** If two updates target the same segment, choose the row with the **latest `updated_at`**. If timestamps tie, use a documented tie-breaker (e.g. lexicographic `gateway_id`, then `id`) so the outcome is stable run to run.
- **Field preservation:** If the “losing” row has non-empty fields the winner does not, optional policy is to merge JSONB keys (last-write-wins per top-level key). That is more work; v1 can be “winner replaces payload” if product accepts it.

### 2.2 SOS

- **No hard deletes from gateway pushes for SOS.** Treat SOS as append-only log: each distinct `id` is inserted once; duplicates on same `id` are ignored (idempotent).
- If the same physical event is filed twice with **different** IDs, the cloud cannot magically dedupe without extra signal (geo + time window). Call that out as a known limitation unless you add a dedupe key from the device.

### 2.3 Supply (if stored like reports)

- Same as road unless stakeholders want “sum quantities” semantics — that is a different merge and must be specified separately.

---

## 3. Duplicate handling across gateways

**Same report `id` pushed twice (retry):** second push should not create a second row. Upsert on `id` or ignore on conflict.

**Same segment, different IDs from two gateways:** merge by `segment_key`; survivor row may need to retain a list of “contributing gateway ids” in `payload` or a side table if audit matters. Minimum bar: one canonical row per segment with latest timestamp.

**SyncLogs:** Every successful batch writes one row with `applied_count` reflecting rows touched after dedupe, not raw incoming length.

---

## 4. Transaction boundaries and failures

**Requirement:** Partial push failures must not leave half a batch applied.

Implementation pattern:

- `BEGIN`
- Insert idempotent `SyncLogs` row in `received` state or use advisory lock on `(gateway_id, batch_id)` for the duration of the transaction.
- Process all items in memory or with staged temp table; collect errors.
- If any hard validation error: `ROLLBACK`, log `failed` with detail (or never commit the log row — pick one story and stick to it).
- If all good: `COMMIT`, status `applied`.

**Partial failures inside one batch:** product choice:

- **Strict (recommended for consistency):** one bad item fails the whole batch; gateway retries corrected batch.
- **Lenient:** return 207-style multi-status (harder for clients). The roadmap asked for rollback on partial failure — interpret that as **strict**.

---

## 5. Code organization

Keep merge out of the route handler:

- `MergeService.apply_batch(batch: SyncBatch) -> MergeResult`
- Pure helpers: `merge_road(existing, incoming) -> MergedRoad`, `merge_sos(...)`

Inline comments (requested documentation) should state **invariants**: e.g. “SOS insert path never executes DELETE,” “segment merge never reduces `updated_at`.”

---

## 6. Testing matrix

### 6.1 Conflict — two gateways, same segment

Setup: segment S, gateway A reports status `ok` at T1, gateway B reports `blocked` at T2 > T1.  
Expect: global row shows `blocked`, `updated_at` = T2, `SyncLogs` shows two successful batches with correct gateway ids.

Tie on timestamp: supply two rows with equal `updated_at`; assert deterministic tie-break.

### 6.2 SOS preservation

Push SOS with id X; push again with same X and altered text; assert **either** immutable first write **or** append-only event log — match what you documented. No row removed.

### 6.3 Rollback

Simulate mid-batch exception (e.g. forced DB error on third item). Assert no rows from that batch committed and `SyncLogs` does not show a successful apply for that batch id (or shows `failed`, consistently).

### 6.4 Idempotent replay

Repeat identical `(gateway_id, batch_id)` body; assert no duplicate SOS, no double-increment of counters, same HTTP semantics (200 with “already applied” flag is fine).

---

## 7. Operational notes

- **Clock skew:** gateways with wrong clocks break “latest wins.” Mitigations: server records `ingested_at`, compare `(updated_at, ingested_at)` with a max skew window, or trust server time for ordering only when device time is unreliable. Document what you implemented.
- **Volume:** large batches need pagination or streaming later; Issue #2 can still assume bounded batch size with a max item count enforced at validation.

---

## 8. Deliverables checklist

- [ ] Merge policy implemented behind `POST /sync/push`.
- [ ] `SyncLogs` records gateway + batch + outcome for every merge.
- [ ] Tests: conflict, SOS idempotency, rollback, replay.
- [ ] Inline comments on invariants and tie-breakers.

---

## 9. Handoff to Issue #4

The integration spike should call the same HTTP API the real gateway will use, with deliberate duplicate batches and overlapping segments, and then query read endpoints (if not yet built, add minimal `GET /reports` for verification behind dev auth only).
