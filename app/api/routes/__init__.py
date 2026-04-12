from fastapi import APIRouter

from app.api.routes import health, models, reports, sync

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
