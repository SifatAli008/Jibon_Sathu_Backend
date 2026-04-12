"""Rate limiting (Issue #8). Keyed by `X-Gateway-Id` when present, else client IP."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def gateway_or_ip_key(request: Request) -> str:
    gid = request.headers.get("X-Gateway-Id")
    if gid:
        return f"gw:{gid}"
    return get_remote_address(request)


limiter = Limiter(key_func=gateway_or_ip_key)
