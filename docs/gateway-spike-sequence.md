# Zone B → Zone A integration spike — sequence (Issue #4)

Routes match this repository’s FastAPI app (`/sync`, `/models`, optional dev `/reports`).

```mermaid
sequenceDiagram
    participant GW as Zone B gateway (sim)
    participant API as Zone A FastAPI
    participant DB as PostgreSQL
    participant FS as Model store (disk)

    GW->>API: POST /sync/push (X-Gateway-Id, X-Sync-Batch-Id, reports[])
    API->>DB: BEGIN; idempotency (gateway_id, batch_id); merge; COMMIT
    API-->>GW: 200 JSON (applied_count, sync_log_status, …)

    opt Dev verification
        GW->>API: GET /reports (X-Dev-Reports-Key)
        API->>DB: SELECT reports …
        API-->>GW: JSON rows (inspect SPIKE-* segments)
    end

    GW->>API: GET /models/road_decay_model/latest
    API->>DB: SELECT model_artifacts WHERE is_latest
    API-->>GW: JSON (version, sha256, size_bytes, …)

    GW->>API: GET /models/road_decay_model/latest/file (optional X-Model-Download-Key)
    API->>FS: read / stream file
    API-->>GW: application/octet-stream (+ ETag)

    GW->>GW: SHA256(file) vs metadata; onnxruntime.InferenceSession smoke
```

See also: [gateway-spike-network-notes.md](gateway-spike-network-notes.md), [samples/gateway-spike-run.txt](samples/gateway-spike-run.txt).
