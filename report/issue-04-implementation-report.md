# Implementation report — Issue #4 (Cloud–gateway integration spike)

**Reference:** [Dev docs/issue-04-cloud-gateway-integration-spike.md](../Dev%20docs/issue-04-cloud-gateway-integration-spike.md)  
**Date:** 2026-04-12  
**Prerequisites:** Issue #2 (`POST /sync/push`, strict transactions, idempotency), Issue #3 (`GET /models/{name}/latest`, `/latest/file`, published artifact).

---

## Deliverables (Issue §7)

| Item | Status | Location |
|------|--------|----------|
| Runnable simulation script (env + CLI) | **Done** | `tools/gateway_sim.py` |
| Example run log (sanitized) | **Done** | [docs/samples/gateway-spike-run.txt](../docs/samples/gateway-spike-run.txt) |
| Sequence diagram in repo | **Done** | [docs/gateway-spike-sequence.md](../docs/gateway-spike-sequence.md) |
| Notes on latency / RST / abort | **Done** | [docs/gateway-spike-network-notes.md](../docs/gateway-spike-network-notes.md) |
| README pointer | **Done** | `README.md` (Issue #4 section) |

---

## What the sim proves

1. **Push + merge:** Ten `reports` include overlapping `segment_key`s; server applies Issue #2 merge inside one transaction; logs include **`batch_id`** for correlation.
2. **Model round-trip:** Metadata `sha256` → streamed download → local hash match → **onnxruntime** smoke inference (requires dev ML stack installed for the script process).
3. **Idempotent retry:** Optional `--repeat-idempotent-push` sends the same batch again and asserts **`idempotent_replay: true`** (safe client retry story).

---

## Exit codes (`tools/gateway_sim.py`)

| Code | Meaning |
|------|--------|
| 0 | Success |
| 1 | HTTP failure or unexpected API response |
| 2 | Downloaded file SHA256 ≠ metadata |
| 3 | `onnxruntime` / `numpy` import or inference failure |

---

## Not in scope (Issue §6)

Real gateway hardware limits, production auth/rate limits, and multi-region failover remain out of scope for this spike; see network notes doc.

---

## Next step (Issue §8)

Promoting this to CI often means: `docker compose up`, publish a tiny ONNX, run `gateway_sim.py` against the container URL (optionally behind toxiproxy), assert exit code **0**.
