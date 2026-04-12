# Gateway spike — latency, aborts, and RST (Issue #4)

This spike proves **happy path + idempotent retry** from a gateway-shaped client. “Chaos” beyond that is **documented here** with concrete knobs; wire-level packet loss is not emulated inside `tools/gateway_sim.py` alone.

## Latency (in-script)

`tools/gateway_sim.py` supports:

- `--sleep-before-push-ms N` — pause before starting `POST /sync/push` (surfaces client-side slowness and server read timeouts if misconfigured).
- `--sleep-ms N` — pause between major steps (push → reports → model metadata → download).

Combine with `httpx` `--timeout` (seconds) to force a **read timeout** on a slow server; the client exits non-zero. Re-run the **same** `batch_id` only after fixing the server: Issue #2 guarantees **no partial commit** on server failure, and a **successful** batch is safe to replay idempotently.

## Client abort mid-upload

`httpx` does not expose a first-class “RST during body” switch in this script. Practical options:

1. **Manual:** start `curl -T large.json --max-time 1 http://.../sync/push` and interrupt (Ctrl+C) while the body is uploading; confirm DB has **no** new rows from that attempt (strict transaction).
2. **Proxy:** [toxiproxy](https://github.com/Shopify/toxiproxy) or similar to close upstream connections mid-request; retry with the **same** `X-Sync-Batch-Id` and expect `idempotent_replay: true` if the first attempt actually committed.

## Connection reset (RST)

Use a TCP proxy or firewall rule to send RST on the client→server path **during** `POST /sync/push`. Expected server behavior: transaction rolled back (Issue #2). Client retries with the same idempotency key once connectivity returns.

## Evidence for reviewers

Record: tool used, command line, HTTP status codes, and whether a **second** identical push returned `idempotent_replay: true`. A sanitized log template lives at [samples/gateway-spike-run.txt](samples/gateway-spike-run.txt).

## Limits of this test (Issue #4 scope)

- Not a substitute for **real gateway** CPU/RAM/flash constraints, **auth/rate limits** at scale, or **multi-region** Postgres failover.
