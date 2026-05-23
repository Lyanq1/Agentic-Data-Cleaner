"""Health check endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session
from app.core.redis_client import get_redis

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Returns 200 if the service is alive."""
    return {"status": "ok"}


@router.get("/readiness", summary="Readiness probe")
async def readiness(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Returns 200 if DB and Redis are reachable."""
    checks = {}
    try:
        await session.execute(__import__("sqlalchemy", fromlist=["text"]).text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
