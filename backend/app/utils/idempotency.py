"""
Redis-based idempotency key management.
Prevents duplicate proxy executions using X-Idempotency-Key header.
"""
import json
import uuid
from app.utils.redis_client import get_redis

IDEM_PREFIX = "idem:"
IDEM_LOCK_PREFIX = "idem_lock:"
IDEM_TTL = 3600  # 1 hour

# Lua script for atomic lock release (same pattern as distributed_lock)
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


async def check_idempotency(key: str) -> dict | None:
    """Check if a response is cached for this idempotency key."""
    redis = await get_redis()
    cached = await redis.get(f"{IDEM_PREFIX}{key}")
    if cached:
        return json.loads(cached)
    return None


async def store_idempotency(key: str, response: dict, ttl: int = IDEM_TTL):
    """Store a response for this idempotency key."""
    redis = await get_redis()
    await redis.setex(f"{IDEM_PREFIX}{key}", ttl, json.dumps(response, default=str))


async def lock_idempotency(key: str, ttl: int = 30) -> str | None:
    """Acquire a lock for this idempotency key. Returns lock_value if acquired, None otherwise."""
    redis = await get_redis()
    lock_value = str(uuid.uuid4())
    acquired = await redis.set(f"{IDEM_LOCK_PREFIX}{key}", lock_value, nx=True, ex=ttl)
    return lock_value if acquired else None


async def unlock_idempotency(key: str, lock_value: str):
    """Release the idempotency lock atomically (only if we still own it)."""
    redis = await get_redis()
    await redis.eval(_RELEASE_SCRIPT, 1, f"{IDEM_LOCK_PREFIX}{key}", lock_value)

