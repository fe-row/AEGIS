"""
Async Redis connection pool.
Provides get_redis() and close_redis() for the application lifecycle.
"""
import redis.asyncio as aioredis
from app.config import get_settings

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create the global async Redis connection."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
    return _redis_client


async def close_redis():
    """Close the Redis connection pool gracefully."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
