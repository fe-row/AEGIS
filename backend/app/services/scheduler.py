"""
Background task scheduler for periodic operations.
Currently handles periodic audit buffer flushing.
"""
import asyncio
from app.logging_config import get_logger
from app.config import get_settings

logger = get_logger("scheduler")
settings = get_settings()

_task: asyncio.Task | None = None
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


def start_scheduler():
    """Start the background scheduler."""
    global _task, _running
    _running = True
    _task = asyncio.create_task(_periodic_flush())
    logger.info("scheduler_started")


def stop_scheduler():
    """Stop the background scheduler gracefully."""
    global _task, _running
    _running = False
    if _task and not _task.done():
        _task.cancel()
    logger.info("scheduler_stopped")
