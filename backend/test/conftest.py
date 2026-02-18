import asyncio
import pytest
import uuid
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-chars-long-for-testing"
os.environ["ENVIRONMENT"] = "test"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_redis():
    """Comprehensive Redis mock."""
    storage: dict[str, str] = {}
    sorted_sets: dict[str, list] = {}

    redis = AsyncMock()

    async def mock_get(key):
        return storage.get(key)

    async def mock_set(key, value, **kwargs):
        if kwargs.get("nx") and key in storage:
            return False
        storage[key] = value
        return True

    async def mock_setex(key, ttl, value):
        storage[key] = value
        return True

    async def mock_delete(*keys):
        for k in keys:
            storage.pop(k, None)
        return len(keys)

    async def mock_rpush(key, value):
        if key not in sorted_sets:
            sorted_sets[key] = []
        sorted_sets[key].append(value)
        return len(sorted_sets[key])

    async def mock_lrange(key, start, end):
        lst = sorted_sets.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]

    async def mock_llen(key):
        return len(sorted_sets.get(key, []))

    async def mock_ltrim(key, start, end):
        if key in sorted_sets:
            sorted_sets[key] = sorted_sets[key][start:end + 1] if end != -1 else sorted_sets[key][start:]
        return True

    redis.get = mock_get
    redis.set = mock_set
    redis.setex = mock_setex
    redis.delete = mock_delete
    redis.rpush = mock_rpush
    redis.lrange = mock_lrange
    redis.llen = mock_llen
    redis.ltrim = mock_ltrim
    redis.ping = AsyncMock(return_value=True)
    redis.sadd = AsyncMock(return_value=1)
    redis.srem = AsyncMock(return_value=1)
    redis.smembers = AsyncMock(return_value=set())
    redis.expire = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.zadd = AsyncMock(return_value=1)
    redis.zrangebyscore = AsyncMock(return_value=[])
    redis.zremrangebyscore = AsyncMock(return_value=0)
    redis.eval = AsyncMock(return_value=1)
    redis.scan = AsyncMock(return_value=(0, []))

    class MockPipeline:
        def __init__(self):
            self._results = []
        def __getattr__(self, name):
            def method(*a, **kw):
                self._results.append(None)
                return self
            return method
        async def execute(self):
            return self._results

    redis.pipeline = lambda: MockPipeline()

    return redis


@pytest.fixture
def sample_ids():
    return {
        "agent_id": uuid.uuid4(),
        "sponsor_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
    }