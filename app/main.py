from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import api_router
from app.db import get_engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    engine = get_engine()
    await engine.dispose()


app = FastAPI(title="Jibon Sathu Cloud API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/")
async def root():
    return {"service": "jibon-sathu-backend", "docs": "/docs"}
