"""gRPC aio server bootstrap (Issue #12)."""

from __future__ import annotations

from typing import Any

import grpc
from grpc import aio as grpc_aio

from app.config import get_settings
from app.grpc_gen import sync_pb2_grpc
from app.grpc_service.ingest import SyncIngestServicer


async def start_grpc_server() -> Any | None:
    settings = get_settings()
    if settings.grpc_port <= 0:
        return None
    server = grpc_aio.server()
    sync_pb2_grpc.add_SyncIngestServicer_to_server(SyncIngestServicer(), server)
    addr = f"[::]:{settings.grpc_port}"
    server.add_insecure_port(addr)
    await server.start()
    return server
