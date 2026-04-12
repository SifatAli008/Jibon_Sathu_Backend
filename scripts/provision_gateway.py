#!/usr/bin/env python3
"""Provision or rotate a gateway shared secret (Issue #7).

Usage:
  DATABASE_URL=postgresql+psycopg2://... python scripts/provision_gateway.py \\
    --gateway-id <uuid> --secret '<plain-secret>'

Requires `psycopg2` (same URL style as Alembic offline scripts) or use asyncpg via app code.
This script uses SQLAlchemy sync engine for simplicity.
"""

from __future__ import annotations

import argparse
import os
import uuid

from sqlalchemy import create_engine, text

from app.deps.gateway_auth import hash_gateway_secret


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gateway-id", required=True)
    p.add_argument("--secret", required=True)
    p.add_argument("--name", default=None)
    args = p.parse_args()

    gid = uuid.UUID(args.gateway_id)
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required (sync URL; use postgresql+psycopg2://...)")

    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")

    h = hash_gateway_secret(args.secret)
    engine = create_engine(url, pool_pre_ping=True)
    name = args.name or f"gateway-{str(gid)[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gateways (id, name, last_seen_at, public_key, auth_secret_hash, revoked_at)
                VALUES (:id, :name, now(), NULL, :h, NULL)
                ON CONFLICT (id) DO UPDATE SET
                  auth_secret_hash = EXCLUDED.auth_secret_hash,
                  revoked_at = NULL,
                  name = EXCLUDED.name
                """
            ),
            {"id": str(gid), "name": name, "h": h},
        )
    engine.dispose()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
