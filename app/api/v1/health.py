"""Health check endpoints."""
from fastapi import APIRouter
from app.core.redis_client import get_redis

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Returns 200 if the service is alive."""
    return {"status": "ok"}


@router.get("/readiness", summary="Readiness probe")
async def readiness() -> dict:
    """Returns 200 if dependent services (Redis) are reachable."""
    checks = {}
    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
    
    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
