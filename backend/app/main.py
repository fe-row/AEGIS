import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

VERSION = "4.0.0"

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.models.database import Base, engine
from app.utils.redis_client import get_redis, close_redis
from app.utils.http_pool import close_http_client
from app.middleware.pure_asgi import AegisMiddlewareStack, RateLimiterASGI
from app.services.policy_engine import policy_engine
from app.services.scheduler import start_scheduler, stop_scheduler
from app.api import auth, agents, wallets, proxy, audit, dashboard, policies
from app.api.websocket import router as ws_router

settings = get_settings()
setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("aegis_starting", version=VERSION, env=settings.ENVIRONMENT)

    if settings.ENVIRONMENT == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    redis = await get_redis()
    await redis.ping()
    logger.info("dependencies_ready")

    start_scheduler()
    yield

    # Graceful shutdown
    logger.info("shutdown_begin")
    stop_scheduler()

    from app.models.database import AsyncSessionLocal
    from app.services.audit_service import AuditService
    try:
        async with AsyncSessionLocal() as db:
            flushed = await AuditService.flush_buffer(db)
            logger.info("shutdown_audit_flushed", count=flushed)
    except Exception as e:
        logger.error("shutdown_flush_error", error=str(e))

    await policy_engine.close()
    await close_http_client()
    await close_redis()
    logger.info("shutdown_complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="Deterministic Execution Proxy for AI Agents",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS (must be outermost Starlette middleware)
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Request-ID", "X-Idempotency-Key", "X-API-Key"],
    expose_headers=["X-Request-ID"],
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routes — must be added BEFORE ASGI middleware wrapping
prefix = settings.API_V1_PREFIX
for r in [auth.router, agents.router, wallets.router, proxy.router,
          audit.router, dashboard.router, policies.router]:
    app.include_router(r, prefix=prefix)
app.include_router(ws_router)


@app.get("/health")
async def health():
    checks = {"api": "ok"}

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
        buf = await redis.llen("audit:buffer")
        proc = await redis.llen("audit:processing")
        checks["audit_queue"] = f"{buf}+{proc}"
    except Exception as e:
        checks["redis"] = f"err:{type(e).__name__}"

    try:
        from sqlalchemy import text
        from app.models.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"err:{type(e).__name__}"

    try:
        from app.utils.http_pool import get_http_client
        client = await get_http_client()
        r = await client.get(f"{settings.OPA_URL}/health", timeout=3)
        checks["opa"] = "ok" if r.status_code == 200 else f"status:{r.status_code}"
    except Exception as e:
        checks["opa"] = f"err:{type(e).__name__}"

    ok = all(v == "ok" for k, v in checks.items() if k not in ("audit_queue",))
    return {"status": "healthy" if ok else "degraded", "version": VERSION, "checks": checks}


# Pure ASGI middleware stack (no BaseHTTPMiddleware) — AFTER routes are registered
app = RateLimiterASGI(app)
app = AegisMiddlewareStack(app)