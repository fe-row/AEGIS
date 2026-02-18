"""
JWT blacklist — FIX: makes logout actually invalidate tokens.
Uses Redis SET with TTL matching token expiry.
"""
from app.utils.redis_client import get_redis
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("jwt_blacklist")
settings = get_settings()


async def blacklist_token(token_jti: str, ttl_seconds: int | None = None):
    """Add a token's JTI to the blacklist."""
    redis = await get_redis()
    ttl = ttl_seconds or (settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    await redis.setex(f"jwt:blacklist:{token_jti}", ttl, "1")
    logger.info("token_blacklisted", jti=token_jti)


async def is_token_blacklisted(token_jti: str) -> bool:
    """Check if a token has been revoked."""
    redis = await get_redis()
    return bool(await redis.exists(f"jwt:blacklist:{token_jti}"))