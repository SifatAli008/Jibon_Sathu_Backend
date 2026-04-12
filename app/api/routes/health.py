from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.db import ping_db
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse | JSONResponse:
    try:
        await ping_db()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "db": "error"},
        )
    return HealthResponse(status="ok", db="ok")
