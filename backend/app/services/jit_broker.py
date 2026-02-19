import uuid
import orjson
from datetime import datetime, timezone
from app.config import get_settings
from app.utils.redis_client import get_redis
from app.utils.crypto import decrypt_secret, generate_ephemeral_token

settings = get_settings()


class JITBroker:
    """Just-In-Time Secret Brokering.
    The agent NEVER touches the real API key. We mint an ephemeral token
    that maps to the real secret, and it auto-expires."""

    def __init__(self):
        pass

    async def mint_ephemeral_token(
        self,
        agent_id: uuid.UUID,
        service_name: str,
        encrypted_secret: str,
        ttl_seconds: int | None = None,
    ) -> str:
        redis = await get_redis()
        ttl = ttl_seconds or settings.JIT_TOKEN_TTL_SECONDS
        ephemeral_token = generate_ephemeral_token()

        real_secret = decrypt_secret(encrypted_secret)

        token_data = {
            "real_secret": real_secret,
            "agent_id": str(agent_id),
            "service_name": service_name,
            "minted_at": datetime.now(timezone.utc).isoformat(),
        }

        key = f"jit:{agent_id}:{ephemeral_token}"
        await redis.setex(key, ttl, orjson.dumps(token_data).decode())

        return ephemeral_token

    async def resolve_token(self, agent_id: uuid.UUID, ephemeral_token: str) -> dict | None:
        """Resolve token by direct key lookup."""
        redis = await get_redis()
        data = await redis.get(f"jit:{agent_id}:{ephemeral_token}")
        return orjson.loads(data) if data else None

    async def revoke_token(self, agent_id: uuid.UUID, ephemeral_token: str):
        redis = await get_redis()
        await redis.delete(f"jit:{agent_id}:{ephemeral_token}")

    async def revoke_all_for_agent(self, agent_id: uuid.UUID):
        """Revoke all active JIT tokens for an agent (panic mode)."""
        redis = await get_redis()
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=f"jit:{agent_id}:*", count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break


jit_broker = JITBroker()