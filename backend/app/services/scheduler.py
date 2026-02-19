"""
Background task scheduler for periodic operations.
Handles audit buffer flushing and secret rotation checks.
"""
import asyncio
from app.logging_config import get_logger
from app.config import get_settings

logger = get_logger("scheduler")
settings = get_settings()

_tasks: list[asyncio.Task] = []
_running = False


async def _periodic_flush():
    """Periodically flush the audit buffer to the database."""
    global _running
    while _running:
        try:
            await asyncio.sleep(settings.AUDIT_FLUSH_INTERVAL_SECONDS)
            if not _running:
                break

            from app.models.database import AsyncSessionLocal
            from app.services.audit_service import AuditService

            async with AsyncSessionLocal() as db:
                flushed = await AuditService.flush_buffer(db)
                if flushed > 0:
                    logger.info("scheduler_audit_flush", count=flushed)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("scheduler_flush_error", error=str(e))
            await asyncio.sleep(5)


async def _periodic_secret_rotation():
    """Periodically check for secrets that need rotation."""
    global _running
    interval = settings.SECRET_ROTATION_CHECK_INTERVAL_HOURS * 3600
    while _running:
        try:
            await asyncio.sleep(interval)
            if not _running:
                break

            from app.models.database import AsyncSessionLocal
            from app.services.secret_rotation import SecretRotationService

            async with AsyncSessionLocal() as db:
                result = await SecretRotationService.check_and_rotate(db)
                if result["rotated"] > 0:
                    logger.info(
                        "scheduler_secret_rotation",
                        rotated=result["rotated"],
                        errors=len(result["errors"]),
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("scheduler_rotation_error", error=str(e))
            await asyncio.sleep(60)


def start_scheduler():
    """Start the background scheduler."""
    global _tasks, _running
    _running = True
    _tasks = [
        asyncio.create_task(_periodic_flush()),
        asyncio.create_task(_periodic_secret_rotation()),
    ]
    logger.info("scheduler_started", tasks=len(_tasks))


def stop_scheduler():
    """Stop the background scheduler gracefully."""
    global _tasks, _running
    _running = False
    for task in _tasks:
        if not task.done():
            task.cancel()
    _tasks.clear()
    logger.info("scheduler_stopped")
