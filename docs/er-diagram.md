# Entity relationship (Zone A, Issue #1)

Mermaid source (renders on GitHub and many Markdown viewers).

```mermaid
erDiagram
    GATEWAYS ||--o{ REPORTS : "sources"
    GATEWAYS ||--o{ SYNC_LOGS : "pushes"

    GATEWAYS {
        uuid id PK
        string name
        timestamptz last_seen_at
        text public_key "nullable"
    }

    REPORTS {
        uuid id PK
        string kind "road|sos|supply"
        jsonb payload
        text segment_key "nullable"
        string status
        timestamptz created_at
        timestamptz updated_at
        uuid source_gateway_id FK "nullable"
        timestamptz deleted_at "nullable"
    }

    SYNC_LOGS {
        bigint id PK
        uuid gateway_id FK
        uuid batch_id
        timestamptz received_at
        int record_count
        int applied_count
        string status
        text error_detail "nullable"
    }
```

**Constraints**

- `SYNC_LOGS (gateway_id, batch_id)` is **unique** (idempotent batch ingest).

**Indexes (summary)**

- `reports (kind, segment_key)`, `reports (updated_at)`, btree indexes on `kind`, `segment_key`, `source_gateway_id` as implemented in Alembic revision `20260412_0001`.
