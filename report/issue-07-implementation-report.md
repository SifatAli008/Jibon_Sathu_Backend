# Implementation report — Issue #7 (Gateway authentication)

**Date:** 2026-04-12  
**Dependencies:** Issue #6 (`GET /sync/pull` exists alongside push).

---

## Deliverables

| Item | Status | Location |
|------|--------|----------|
| `gateways.auth_secret_hash`, `gateways.revoked_at` | **Done** | `alembic/versions/20260412_0004_gateway_auth_merge_audit.py`, `app/models/gateway.py` |
| FastAPI dependency (`X-Gateway-Id` + `Authorization: Bearer …`) | **Done** | `app/deps/gateway_auth.py` |
| Applied to `POST /sync/push`, `GET /sync/pull` | **Done** | `app/api/routes/sync.py` |
| Applied to `GET /models/{name}/latest` (+ file when auth enabled) | **Done** | `app/api/routes/models.py` |
| Provisioning script | **Done** | `scripts/provision_gateway.py` |
| Documentation | **Done** | `SECURITY_MODEL.md`, `API_SPEC.md` |
| Tests (401/403/200 paths) | **Done** | `tests/test_issues_5_8.py` |

---

## Configuration

- `REQUIRE_GATEWAY_AUTH` (default **false** locally): set **true** in production.
- When disabled, sync routes still require `X-Gateway-Id` for identity/rate-limit keys, but **no bearer token** is validated.

---

## Merge interaction

When `REQUIRE_GATEWAY_AUTH=true`, `POST /sync/push` no longer “auto-creates” unknown gateways; gateways must be provisioned first (secret hash present).
