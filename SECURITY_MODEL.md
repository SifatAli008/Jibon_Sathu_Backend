# Gateway security model (Issue #7)

This document describes how Zone A authenticates Zone B Gateways for sync and model metadata/download endpoints.

## Threat model (practical)

- Networks in disaster zones may be hostile or shared; **spoofed `X-Gateway-Id`** headers must not be sufficient.
- Compromised gateways must be **revocable quickly** without redeploying the whole fleet schema.

## Provisioning

1. Create a **random high-entropy secret** per gateway (treat like an API key).
2. Store only a **bcrypt hash** in Postgres: `gateways.auth_secret_hash`.
3. Distribute the raw secret to the gateway operator through an out-of-band channel (not committed to git).

This repo includes a helper script:

```bash
DATABASE_URL=postgresql+psycopg2://jibon:jibon@127.0.0.1:5433/jibon_sathu \
  python scripts/provision_gateway.py --gateway-id <UUID> --secret '<secret>'
```

## Request authentication

When `REQUIRE_GATEWAY_AUTH=true`, protected routes require:

- `X-Gateway-Id: <uuid>`
- `Authorization: Bearer <plain-secret>`

The server verifies the bearer secret against `auth_secret_hash`.

## Revocation

Set `gateways.revoked_at` to a non-null timestamp. The gateway should receive **403 Forbidden** on all authenticated routes immediately after revocation.

To restore access: clear `revoked_at` and optionally rotate the secret by updating `auth_secret_hash`.

## Key rotation

1. Provision a **new secret** (update `auth_secret_hash` in the database).
2. Roll out the new secret to the gateway.
3. Optionally revoke old sessions by relying on a single active secret (simplest operational model).

If you need overlap (two valid secrets), extend the schema (e.g., `auth_secret_hash_2` + `secret_version`) — not implemented in the baseline Issue #7 delivery.

## Public keys

`gateways.public_key` remains available for future asymmetric schemes (e.g., signed payloads). The baseline implementation uses **shared-secret bearer tokens** for simplicity in intermittent networks.

## Dashboard admin (Issue #13)

When **`DASHBOARD_ADMIN_KEY`** is set in the server environment, **`GET /v1/analytics/*`** requires header **`X-Dashboard-Admin-Key`** with the same value. If the key is unset, the analytics routes are **disabled** (same pattern as other dev/admin endpoints).

## gRPC client version (Issue #12)

gRPC calls to **`SyncIngest.PushBatch`** must include **`x-client-version`** or **`x-gateway-version`** metadata (semver). The server rejects requests below **`GRPC_MIN_CLIENT_VERSION`** (default **`1.0.0`**) with **FAILED_PRECONDITION**. This is independent of gateway bearer auth; it guards field clients against incompatible server builds.
