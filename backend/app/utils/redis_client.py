"""
Redis client — supports both standalone and Sentinel modes.
"""
import redis.asyncio as aioredis
from typing import Optional

from app.config import get_settings
from app.logging_config import get_logger

settings = get_settings()
logger = get_logger("redis")

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        # Sentinel mode
        if settings.REDIS_SENTINEL_HOSTS:
            sentinels = []
            for host_port in settings.REDIS_SENTINEL_HOSTS.split(","):
                host_port = host_port.strip()
                if ":" in host_port:
                    host, port = host_port.rsplit(":", 1)
                    sentinels.append((host, int(port)))
                else:
                    sentinels.append((host_port, 26379))

            sentinel = aioredis.Sentinel(
                sentinels,
                password=settings.REDIS_URL.split(":")[2].split("@")[0] if "@" in settings.REDIS_URL else None,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
            )
            _redis = sentinel.master_for(settings.REDIS_SENTINEL_MASTER)
            logger.info(
                "redis_sentinel_connected",
                master=settings.REDIS_SENTINEL_MASTER,
                sentinels=len(sentinels),
            )
        else:
            # Standalone mode (existing behavior)
            _redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
            )
            logger.info("redis_standalone_connected")

    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("redis_closed")
