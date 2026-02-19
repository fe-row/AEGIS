"""
Pure ASGI middleware — FIX: BaseHTTPMiddleware breaks
StreamingResponse, WebSocket, and has memory issues.
"""
import hashlib
import time
import uuid
import contextvars
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import Response
from app.utils.redis_client import get_redis
from app.config import get_settings
from app.logging_config import get_logger
from app.utils.metrics import REQUEST_COUNT, REQUEST_LATENCY

settings = get_settings()
logger = get_logger("middleware")

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    return correlation_id_var.get()


class AegisMiddlewareStack:
    """
    Single ASGI middleware that handles:
    1. Correlation ID
    2. Security headers
    3. Request size limit
    4. Request metrics
    Combines all into one to avoid nested middleware overhead.
    """

    SKIP_PATHS = frozenset({"/health", "/metrics", "/docs", "/openapi.json", "/redoc"})
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # WebSocket — only set correlation ID, skip the rest
        if scope["type"] == "websocket":
            token = correlation_id_var.set(str(uuid.uuid4())[:12])
            try:
                await self.app(scope, receive, send)
            finally:
                correlation_id_var.reset(token)
            return

        # HTTP request
        request = Request(scope)
        path = request.url.path

        # Set correlation ID
        req_id = (request.headers.get("x-request-id") or str(uuid.uuid4())[:12])
        token = correlation_id_var.set(req_id)

        start_time = time.monotonic()

        # Check content-length before processing
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            response = Response(
                content='{"code":"REQUEST_TOO_LARGE","message":"Body exceeds 10MB"}',
                status_code=413,
                media_type="application/json",
            )
            await response(scope, receive, send)
            correlation_id_var.reset(token)
            return

        # Wrap send to inject headers
        response_started = False
        status_code = 200

        async def send_with_headers(message):
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message.get("status", 200)
                headers = dict(message.get("headers", []))

                # Security headers
                extra_headers = [
                    (b"x-request-id", req_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]

                existing = list(message.get("headers", []))
                existing.extend(extra_headers)
                message = {**message, "headers": existing}

            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            # Record metrics (skip health/metrics paths)
            if path not in self.SKIP_PATHS:
                duration = time.monotonic() - start_time
                parts = path.split("/")
                norm = "/".join(
                    "{id}" if (len(p) == 36 and p.count("-") == 4) else p
                    for p in parts
                )
                method = scope.get("method", "GET")
                REQUEST_COUNT.labels(method=method, path=norm, status=status_code).inc()
                REQUEST_LATENCY.labels(method=method, path=norm).observe(duration)

            correlation_id_var.reset(token)


class RateLimiterASGI:
    """
    Pure ASGI rate limiter — FIX: uses INCR+EXPIRE (O(1))
    instead of sorted sets (O(log n) + memory leak).
    Falls back to in-memory counter if Redis is unavailable.
    """

    # In-memory fallback when Redis is down
    _fallback_counters: dict[str, int] = {}
    _fallback_window: int = 0

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        if path in AegisMiddlewareStack.SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        # Determine limit
        is_auth = path.startswith(f"{settings.API_V1_PREFIX}/auth")
        limit = settings.AUTH_RATE_LIMIT_PER_MINUTE if is_auth else settings.GLOBAL_RATE_LIMIT_PER_MINUTE

        # Build identity key
        client_ip = scope.get("client", ("unknown", 0))[0]
        auth = dict(scope.get("headers", [])).get(b"authorization", b"").decode()
        auth_hash = hashlib.sha256(auth.encode()).hexdigest()[:12] if auth else "anon"
        identity = f"{client_ip}:{auth_hash}"

        try:
            redis = await get_redis()
            window = 60
            now_window = str(int(time.time()) // window)
            key = f"rl:{identity}:{path}:{now_window}"

            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window + 5)
            results = await pipe.execute()
            current = results[0]

            if current > limit:
                response = Response(
                    content=f'{{"code":"RATE_LIMITED","message":"Limit: {limit}/min"}}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "60"},
                )
                await response(scope, receive, send)
                return

        except Exception as e:
            # SECURITY FIX: Fall back to in-memory rate limiting instead of fail-open
            logger.error("rate_limiter_redis_down", error=str(e))
            current_window = int(time.time()) // 60
            if current_window != RateLimiterASGI._fallback_window:
                RateLimiterASGI._fallback_counters.clear()
                RateLimiterASGI._fallback_window = current_window

            fallback_key = f"{identity}:{path}"
            RateLimiterASGI._fallback_counters[fallback_key] = (
                RateLimiterASGI._fallback_counters.get(fallback_key, 0) + 1
            )
            # Conservative limit when Redis is down
            if RateLimiterASGI._fallback_counters[fallback_key] > min(limit, 30):
                response = Response(
                    content='{"code":"RATE_LIMITED","message":"Rate limit exceeded (degraded mode)"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "60"},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)