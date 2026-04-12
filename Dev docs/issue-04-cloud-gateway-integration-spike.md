# Issue #4 — Cloud–Gateway Integration Spike

**Digital Delta · Zone B → Zone A**  
**Prerequisites:** Issue #2 (merge + transactional push) and Issue #3 (model metadata + download).  
**Purpose:** Prove the architecture link before hardware and real gateways arrive. This is a controlled rehearsal, not production load testing.

---

## 1. What you are proving

1. A gateway-shaped client can push a batch of road reports (ten is enough) and those reports appear in Postgres the way merge policy says they should.
2. The same client can discover the latest ONNX model version, download it, and verify it locally.
3. The server does something **reasonable** when the network misbehaves: no corrupted partial batches on the server side (strict transactions from Issue #2), and the client can retry safely.

---

## 2. Simulation script

**Language:** Python 3.11+ recommended to match the rest of the stack.

**Location:** e.g. `tools/gateway_sim.py` or `scripts/zone_b_simulation.py`

**Configuration:** base URL, gateway UUID, optional HTTP timeout, optional TLS verify flag for dev certs.

**Flow:**

1. Mint a `batch_id`.
2. Build ten `reports` payloads with intentional overlaps (e.g. two updates to same `segment_key` with different timestamps) so you can manually inspect merge output in the DB or via a read API.
3. `POST /sync/push` with headers `X-Gateway-Id`, `X-Sync-Batch-Id`.
4. Parse response; exit non-zero on error.
5. `GET /models/road_decay/latest` — print version and hash.
6. `GET .../latest/file` — stream to disk.
7. Compute SHA256; compare to metadata; load with onnxruntime.

**Logging:** human-readable timestamps and correlation ids (batch_id) so when something fails you can grep server logs the same way ops would in the field.

---

## 3. Latency and “dropped packets” simulation

The roadmap asks for high latency and dropped packets. Interpret that practically:

**Latency:** wrap the HTTP client with configurable sleep or use a proxy (toxiproxy, clumsy on Windows, etc.). For a spike, `httpx` with high read/write timeouts plus `time.sleep` between chunks is often enough to surface server-side timeout misconfiguration.

**Dropped packets / mid-request failure:**

- **Client abort:** start upload, cancel mid-body (if your client library supports it). Server should not commit partial batch (Issue #2 strict transaction).
- **Connection reset:** use a reverse proxy or firewall rule to RST active connections during POST; client retries with same `batch_id` and must get idempotent behavior.

Document what you actually ran; “we simulated chaos” without commands is weak evidence for reviewers.

---

## 4. Acceptance evidence

| Check | Evidence |
|--------|----------|
| Data merged | SQL query or `GET` showing expected canonical rows for overlapping pushes |
| Model round-trip | Local file hash matches API + InferenceSession loads |
| Bad network | Short write-up: what tool, what observed server behavior, client retry outcome |

---

## 5. Sequence diagram (documentation artifact)

Use Mermaid in `docs/` so it versions with code:

```mermaid
sequenceDiagram
    participant GW as Zone B Gateway (sim)
    participant API as Zone A FastAPI
    participant DB as PostgreSQL
    participant FS as Model store

    GW->>API: POST /sync/push (batch_id, reports)
    API->>DB: BEGIN; idempotency check; merge; COMMIT
    API-->>GW: 200 + applied counts

    GW->>API: GET /models/.../latest
    API->>DB: read version row
    API-->>GW: JSON version + sha256

    GW->>API: GET /models/.../latest/file
    API->>FS: stream bytes
    API-->>GW: application/octet-stream
    GW->>GW: verify hash; onnxruntime load
```

Adjust names to match your real routes.

---

## 6. What this spike explicitly does not replace

- Real gateway firmware constraints (CPU, RAM, disk wear).
- Authentication hardening and rate limits at scale.
- Multi-region Postgres and failover (if “Always Online” later means more than one AZ).

Call those out in a short “limits of this test” paragraph in the same doc or README so stakeholders do not over-read the results.

---

## 7. Deliverables checklist

- [ ] Runnable simulation script with config via env or CLI flags.
- [ ] Example run log (sanitized) attached to ticket or committed as `docs/samples/gateway-spike-run.txt` if policy allows.
- [ ] Sequence diagram checked into repo.
- [ ] Notes on latency/RST tests and server responses.

---

## 8. Closing the loop on the roadmap

After Issue #4 passes, you have a thin vertical slice: **schema + API + merge + model + client proof**. The remaining SDLC gap from the original write-up — formal integration tests under intermittent connectivity — becomes a **repeatable CI job** (docker-compose up, run spike with toxiproxy, assert exit code). That promotion from “spike” to “pipeline” is usually the next ticket, not this one.
