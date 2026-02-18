"""
Shared httpx connection pool — FIX: prevents socket exhaustion
from creating new AsyncClient per proxy request.
"""
import httpx
from app.logging_config import get_logger

logger = get_logger("http_pool")

_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,
            max_redirects=0,
            limits=httpx.Limits(
                max_connections=200,
                max_keepalive_connections=50,
                keepalive_expiry=30.0,
            ),
        )
        logger.info("http_pool_created")
    return _client


async def close_http_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
        logger.info("http_pool_closed")