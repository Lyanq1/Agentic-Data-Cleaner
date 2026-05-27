"""Async Redis client manager."""
import redis.asyncio as redis
from app.config.config import get_settings

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return the cached async Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client

async def close_redis() -> None:
    """Close the Redis client gracefully."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
