from fastapi import APIRouter

from app.api.routes import health, models, reports, sync

api_router = APIRouter()

# V1 external contract (Issue #10): sync + models are versioned; health + dev reports stay at root.
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(sync.router, prefix="/sync", tags=["sync"])
v1_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(v1_router)

api_router.include_router(health.router, tags=["health"])
api_router.include_router(reports.router, tags=["reports"])
