# Implementation report — Issue #12 (gRPC bridge)

**Date:** 2026-04-12  
**Dependencies:** Issue #10, #11 (enqueue parity).

---

## Deliverables

| Item | Status | Location |
|------|--------|----------|
| `sync.proto` | **Done** | `protos/sync.proto` |
| Stub generation | **Done** | `scripts/gen_grpc_stubs.py`, `app/grpc_gen/` |
| `SyncIngest.PushBatch` | **Done** | `app/grpc_service/ingest.py` → `MergeService.apply_batch` |
| In-process gRPC server | **Done** | `app/grpc_service/server.py`, `app/main.py` lifespan (`GRPC_PORT`, `0` = off) |
| Client version metadata | **Done** | `x-client-version` / `x-gateway-version` vs `GRPC_MIN_CLIENT_VERSION` |
| Tests | **Done** | `tests/test_issues_11_13.py`, `tests/test_grpc_rest_parity.py` |

---

## Parity

`tests/test_grpc_rest_parity.py` compares persisted `reports` rows for the same logical batch via REST vs gRPC (unique `segment_key`).
