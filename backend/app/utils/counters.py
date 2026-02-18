"""
Redis atomic counters — FIX: replaces O(n) buffer scan
with O(1) INCR-based hourly counters.
"""
import uuid
from app.utils.redis_client import get_redis
from datetime import datetime, timezone


async def increment_hourly_counter(
    agent_id: uuid.UUID,
    service_name: str,
) -> int:
    """Atomically increment and return current hourly request count."""
    redis = await get_redis()
    now = datetime.now(timezone.utc)
    key = f"counter:hourly:{agent_id}:{service_name}:{now.strftime('%Y%m%d%H')}"

    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 7200)  # 2 hours TTL
    results = await pipe.execute()
    return results[0]


async def get_hourly_count(
    agent_id: uuid.UUID,
    service_name: str,
) -> int:
    """Get current hourly count without incrementing."""
    redis = await get_redis()
    now = datetime.now(timezone.utc)
    key = f"counter:hourly:{agent_id}:{service_name}:{now.strftime('%Y%m%d%H')}"
    val = await redis.get(key)
    return int(val) if val else 0