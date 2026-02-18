"""
Distributed lock using Redis SET NX.
Used by audit_service.py to prevent concurrent flush operations.
"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from app.utils.redis_client import get_redis

LOCK_PREFIX = "lock:"

# Lua script: atomically release lock only if we still own it
_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


@asynccontextmanager
async def distributed_lock(
    name: str,
    ttl_seconds: int = 10,
    retry_count: int = 3,
    retry_delay: float = 0.3,
):
    """
    Async context manager for distributed locking via Redis.
    Raises RuntimeError if lock cannot be acquired.
    """
    redis = await get_redis()
    lock_key = f"{LOCK_PREFIX}{name}"
    lock_value = str(uuid.uuid4())
    acquired = False

    for _ in range(retry_count):
        acquired = await redis.set(lock_key, lock_value, nx=True, ex=ttl_seconds)
        if acquired:
            break
        await asyncio.sleep(retry_delay)

    if not acquired:
        raise RuntimeError(f"Could not acquire lock: {name}")

    try:
        yield
    finally:
        # Atomically release only if we still own the lock (Lua script)
        await redis.eval(_RELEASE_SCRIPT, 1, lock_key, lock_value)

