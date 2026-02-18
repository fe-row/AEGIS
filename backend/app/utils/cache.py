"""
Redis-based permission cache for agent permissions.
Avoids repeated DB lookups on every proxy execution.
"""
import json
import uuid
from app.utils.redis_client import get_redis

CACHE_PREFIX = "perm:"
CACHE_TTL = 300  # 5 minutes


def _cache_key(agent_id: uuid.UUID, service_name: str) -> str:
    return f"{CACHE_PREFIX}{agent_id}:{service_name}"


async def get_cached_permission(agent_id: uuid.UUID, service_name: str) -> dict | None:
    """Get cached permission dict, or None if not cached."""
    redis = await get_redis()
    cached = await redis.get(_cache_key(agent_id, service_name))
    if cached:
        return json.loads(cached)
    return None


async def set_cached_permission(agent_id: uuid.UUID, service_name: str, permission: dict):
    """Cache a permission dict with TTL."""
    redis = await get_redis()
    await redis.setex(
        _cache_key(agent_id, service_name),
        CACHE_TTL,
        json.dumps(permission, default=str),
    )


async def invalidate_cached_permission(agent_id: uuid.UUID, service_name: str):
    """Remove a cached permission entry (call on permission add/update/delete)."""
    redis = await get_redis()
    await redis.delete(_cache_key(agent_id, service_name))
