# Zone A architecture audit (repository vs diagram)

**Scope:** This audit compares the **Jibon Sathu Backend** repository (this codebase) to the **Zone A — Cloud layer** diagram you provided: FastAPI → PostgreSQL → Celery/Redis → ML training, plus the stakeholder dashboard layer.

**Method:** Static review of dependencies (`pyproject.toml`, `docker-compose.yml`), application entrypoints (`app/main.py`), routes, models, and services. No production deployment or runtime profiling was performed.

---

## Executive summary

| Diagram area | Alignment with this repo |
|--------------|---------------------------|
| **FastAPI + Uvicorn + REST** | **Strong** — primary API is FastAPI; JSON/REST under `/v1/`. |
| **gRPC endpoints** | **Not present** — no gRPC services or stubs in this repository. |
| **PostgreSQL — merged state** | **Strong** — `reports` with merge policy, `server_sequence_id`, tombstones. |
| **PostgreSQL — audit log** | **Partial** — `sync_logs` + optional `merge_audit` JSON; not a full immutable audit log product. |
| **Celery + Redis (M6 triage broker)** | **Not present** — no Celery, Redis, or async job workers in repo or Compose. |
| **ML training + M7 ONNX export** | **Partial** — offline **export** scripts (`app/ml/onnx_export.py`, `scripts/export_road_decay_onnx.py`) and **publish** to DB/disk; no in-cloud training loop or scheduled retrain. |
| **Stakeholder dashboard (React, Leaflet)** | **Out of repo** — not implemented here; this backend is API-only. |
| **Dashboard “REST/JSON permitted here only”** | **N/A to this repo** — would be a frontend/API policy decision elsewhere. |

**Bottom line:** This repository **implements the API gateway + Postgres persistence + ONNX artifact registry** slice of Zone A. It does **not** implement Celery/Redis triage, gRPC, live ML training in the cloud, or the React/Leaflet dashboard.

---

## 1. Processing pipeline (diagram top row)

### 1.1 FastAPI server (Python, Uvicorn, REST + gRPC)

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Python + FastAPI | `app/main.py`, `app/api/routes/*` | **Met** |
| Uvicorn | Documented in `README.md`; standard ASGI server | **Met** (ops choice, not pinned as a library in `dependencies` beyond `uvicorn[standard]`) |
| REST / JSON | `/v1/sync/*`, `/v1/models/*`, `/health`, dev `/reports` | **Met** |
| gRPC | Grep: no `grpc` usage | **Not met** |

**Note:** Versioned public API is under **`/v1/`** (Issue #10); health remains at **`/health`**.

---

### 1.2 PostgreSQL — CRDT merged state & audit

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Primary DB | `docker-compose.yml` Postgres 16; SQLAlchemy/asyncpg | **Met** |
| Merged distributed state | `app/services/merge_service.py`, `merge_policy.py`; segment-key LWW + tombstone rules | **Met** (CRDT-style **tombstones** + **server sequence** ordering, not a full CRDT library) |
| Monotonic server ordering | `server_sequence_global`, `reports.server_sequence_id`, `app/services/server_sequence.py` | **Met** |
| Tombstones / zombie prevention | `reports.is_tombstone`, merge policy when canonical is tombstone | **Met** |
| Audit log | `sync_logs` per batch; `merge_audit` JSON for resolution events (Issues #7–#8) | **Partial** — operational/merge audit, not necessarily a legal-grade append-only audit store |
| Full audit for stakeholder “full audit trail” UI | No dedicated read model or export API beyond `/v1/sync/conflicts` (admin-gated) | **Gap** vs diagram ambition |

---

### 1.3 Celery + Redis — async triage (M6) job broker

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Celery | Not in `pyproject.toml`; no tasks package | **Not met** |
| Redis | Not in `docker-compose.yml` or dependencies | **Not met** |
| Job broker / triage queue | No workers, no queues | **Not met** |

**Implication:** Any “M6 triage” in the diagram is **not implemented in this repository**. It would be a **separate service** or future work.

---

### 1.4 ML training — scikit-learn, M7 ONNX export

| Claim | Evidence | Verdict |
|-------|----------|---------|
| scikit-learn / export path | `app/ml/onnx_export.py`, dev deps `scikit-learn`, `skl2onnx` | **Met for offline export** |
| ONNX artifacts | `model_artifacts` table; `scripts/publish_model.py`; `GET /v1/models/{name}/latest` | **Met** |
| Compatibility metadata | `min_gateway_version`, `input_schema_hash` (Issue #9) | **Met** |
| Continuous / cloud **training** in Zone A | No training pipelines, notebooks, or schedulers in repo | **Not met** — training is assumed **out-of-band** (scripts run by operators), not a always-on “ML training” service as in the diagram |

---

## 2. Stakeholder dashboard (diagram bottom row)

| Claim | Evidence | Verdict |
|-------|----------|---------|
| React + Leaflet | No frontend in this repo | **Out of scope / not implemented here** |
| Aggregated heatmap, ML overlay, fleet status, SLA alerts | No APIs dedicated to these features | **Not met** in this backend |
| REST/JSON only for dashboard | Backend exposes JSON REST; no dashboard app to enforce policy | **N/A** at this layer |

**Integration note:** A future dashboard would typically consume **`GET /v1/sync/pull`** (or a dedicated admin API), **`GET /v1/models/...`**, and possibly **`GET /v1/sync/conflicts`** — only a subset of what the diagram lists as dashboard capabilities.

---

## 3. Cross-cutting concerns (from diagram + your issues)

| Topic | Status in repo |
|-------|----------------|
| **Data integrity / `server_sequence_id`** | Implemented — see migrations `20260412_0003` and merge/pull logic. |
| **ONNX compatibility (Issue #9)** | Implemented on publish + latest + pull metadata. |
| **API versioning `/v1` (Issue #10)** | Implemented — legacy unversioned sync routes return 404. |
| **Conflict / resolution observability** | `merge_audit` on `sync_logs`; admin **`GET /v1/sync/conflicts`**. |
| **Rate limiting / gateway auth** | slowapi, gateway bearer auth optional, `SECURITY_MODEL.md`. |

---

## 4. Gaps and recommendations (prioritized)

1. **Diagram vs repo scope** — Treat this repository as **Zone A API + Postgres + model registry**, not the full diagram. Update the diagram or a README in the org wiki to show **what is in-repo vs planned**.
2. **gRPC** — If gRPC is required for internal services, add a separate spec (protobuf, services) and optionally run alongside FastAPI or behind a proxy; **nothing exists yet**.
3. **Celery + Redis + M6 triage** — If still required, add `redis` + `celery` to infrastructure, define task contracts, and wire PostgreSQL events or outbox pattern; **greenfield** relative to current code.
4. **Audit trail for HQ/NGO** — Extend beyond `sync_logs` if you need **long-retention, queryable** audit (e.g., immutable event table, correlation IDs, report-level history).
5. **Dashboard** — Implement as a separate frontend repo; align on **which** backend endpoints power heatmap vs fleet vs SLA (most of that is **not** in this API yet).
6. **ML training block** — Clarify: **offline training + publish** (current) vs **managed training service** (diagram). The latter is not in this codebase.

---

## 5. Artifact reference (quick map)

| Diagram block | Closest code / docs |
|---------------|---------------------|
| FastAPI | `app/main.py`, `app/api/routes/` |
| PostgreSQL state | `app/models/`, `alembic/versions/` |
| REST sync | `app/api/routes/sync.py`, `app/services/merge_*.py` |
| ONNX / models | `app/api/routes/models.py`, `app/models/model_artifact.py`, `scripts/` |
| Ops / contracts | `API_SPEC.md`, `README.md`, `SECURITY_MODEL.md` |

---

*Audit produced for the Zone A cloud layer diagram (FastAPI → Postgres → Celery/Redis → ML training; React/Leaflet dashboard). This file is descriptive and does not change runtime behavior.*
