from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.redis import close_redis
from app.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The user must create/configure PostgreSQL and the vector extension first.
    await init_db()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        ) as client:
            app.state.http_client = client
            yield
    finally:
        await close_redis()
        await close_db()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Student-ID"],
)
app.include_router(health_router)
app.include_router(chat_router, prefix="/api")
