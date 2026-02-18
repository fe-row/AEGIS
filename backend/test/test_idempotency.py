import pytest
from unittest.mock import patch, AsyncMock
from app.utils.idempotency import check_idempotency, store_idempotency, lock_idempotency


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_no_key_returns_none(self):
        result = await check_idempotency("")
        assert result is None

    @pytest.mark.asyncio
    async def test_lock_empty_key(self):
        result = await lock_idempotency("")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_miss(self, mock_redis):
        with patch("app.utils.idempotency.get_redis", return_value=mock_redis):
            result = await check_idempotency("test-key-123")
            assert result is None

    @pytest.mark.asyncio
    async def test_store_and_check(self, mock_redis):
        import json
        response = {"status": "executed", "request_id": "abc"}
        with patch("app.utils.idempotency.get_redis", return_value=mock_redis):
            await store_idempotency("key1", response)
            # Simulate cache hit
            mock_redis.get = AsyncMock(return_value=json.dumps(response))
            result = await check_idempotency("key1")
            assert result == response