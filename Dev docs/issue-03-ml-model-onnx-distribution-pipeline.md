# Issue #3 — ML Model (ONNX) Distribution Pipeline

**Digital Delta · Zone A (Cloud)**  
**Prerequisite:** Issue #1 application shell and database (you need somewhere to record model versions).  
**Intent:** Training happens in the cloud; gateways pull a binary they can run with onnxruntime during narrow sync windows. Bandwidth matters, so version checks should precede full downloads.

---

## 1. Pipeline overview

1. **Train** a placeholder scikit-learn model (e.g. `RandomForestRegressor` or a small classifier standing in for “road decay”).
2. **Export** to ONNX with `skl2onnx` (or equivalent) with explicit input/output names and opset compatible with your gateway runtime.
3. **Store** the `.onnx` file on disk or object storage; **record** metadata in Postgres.
4. **Serve** via FastAPI: metadata endpoint + file download endpoint.
5. **Verify** in CI with onnxruntime load + optional inference smoke.

Object storage (S3-compatible) is the long-term fit; local filesystem under a configured path is acceptable for the first milestone if you document backup and permissions.

---

## 2. Database: model versions

Minimal table `model_artifacts`:

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID or bigserial | Surrogate. |
| `name` | text | e.g. `road_decay_model` |
| `version` | text | Semver or monotonic string (`2026.04.12-1`). |
| `created_at` | timestamptz | When promoted. |
| `file_sha256` | char(64) | Integrity for gateways and caches. |
| `file_size_bytes` | bigint | For progress UI and CDN. |
| `storage_path` | text | Relative path on disk or object key. |
| `is_latest` | bool | Only one row per `name` should be true; enforce in transaction when publishing. |

Alternative: no `is_latest` flag; derive latest by `created_at` desc. Flag simplifies `GET /models/latest` but adds update logic.

---

## 3. Export script

**Location:** e.g. `scripts/export_road_decay_onnx.py`

**Behavior:**

- Build sklearn model (fixed random seed for reproducible tests).
- Define `initial_types` matching what the gateway will send (e.g. float tensor `[None, F]`).
- Write `artifacts/models/road_decay_model.onnx` (path configurable).
- Print `sha256` and suggested `version` string for the operator to insert into DB or pass to a small “publish” CLI.

**Do not** commit multi-megabyte binaries if your team policy forbids it; some teams store only hashes and fetch from release artifacts. For acceptance (“valid binary”), a small tracked file or CI-generated artifact is enough if documented.

---

## 4. HTTP API

### Version probe (save bandwidth)

`GET /models/road_decay/latest` (name in path or query)

Response JSON example:

```json
{
  "name": "road_decay_model",
  "version": "2026.04.12-1",
  "sha256": "…",
  "size_bytes": 123456,
  "updated_at": "2026-04-12T12:00:00Z"
}
```

Gateway compares `sha256` (or version string) to local cache; skips download if match.

### Download

`GET /models/road_decay/latest/file`  
Headers: `Content-Type: application/octet-stream`, `Content-Disposition` with filename, optional `ETag` from hash for HTTP caching.

**Streaming:** use `FileResponse` with chunk size or async iterator for large files so memory stays flat under load tests.

---

## 5. Security and operations

- **Auth:** public read may be unacceptable; at minimum gate downloads behind the same gateway auth you use for `/sync/push` when that exists.
- **Integrity:** gateways should verify SHA256 after download against the metadata call.
- **Rollback:** publishing a new “latest” should be a single transaction updating flags / inserting row so gateways never see a half-published state.

---

## 6. Testing

**ONNX validity**

- Load with `onnxruntime.InferenceSession` in pytest.
- Run one forward pass with dummy input shaped like training features.

**HTTP**

- Download endpoint returns 200, body length matches `file_size_bytes`.
- Streaming test: large temp file, assert memory high-water stays reasonable (rough heuristic) or simply assert chunked read works.

**Caching**

- If `ETag` implemented, conditional GET returns 304.

---

## 7. README updates (required)

Add a short section for whoever retrains:

- Where the training script lives (or point to external notebook repo).
- Command to export ONNX.
- Command or admin API to register a new version as latest.
- Ops note: restart not required if serving from disk and process caches path — or clear cache if you implement one.

---

## 8. Deliverables checklist

- [ ] `sklearn` placeholder + export script producing valid ONNX.
- [ ] DB table and migration for versions.
- [ ] `GET .../latest` metadata JSON.
- [ ] `GET .../latest/file` binary response with streaming.
- [ ] Pytest + onnxruntime verification.
- [ ] README section for retrain and redeploy.

---

## 9. Handoff to Issue #4

The gateway simulation should: call metadata, optionally skip download, then download to a temp path, hash the file, compare to advertised `sha256`, and load with onnxruntime. That proves the round-trip the architecture diagram promises.
