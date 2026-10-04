from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.redis import redis_client
from app.db.session import SessionLocal


router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Basic liveness route without dependency checks."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    checks = {"database": False, "redis": False}
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            checks["database"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(await redis_client.ping())
    except Exception:
        pass
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "unavailable", "checks": checks},
    )
