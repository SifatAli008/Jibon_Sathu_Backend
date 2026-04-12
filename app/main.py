from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import api_router
from app.db import dispose_db_engine
from app.grpc_service.server import start_grpc_server
from app.limits import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    grpc_server = await start_grpc_server()
    app.state.grpc_server = grpc_server
    yield
    if grpc_server is not None:
        await grpc_server.stop(grace=5.0)
    await dispose_db_engine()


app = FastAPI(title="Jibon Sathu Cloud API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc: RateLimitExceeded):  # type: ignore[no-untyped-def]
    retry_after = getattr(exc, "retry_after", None) or 60
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
        headers={"Retry-After": str(retry_after)},
    )


app.include_router(api_router)


@app.get("/")
async def root():
    return {"service": "jibon-sathu-backend", "docs": "/docs"}
