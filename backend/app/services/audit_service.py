"""
Audit Service v4 — FIX: uses RPOPLPUSH pattern to prevent data loss.
Entries move from buffer → processing list → DB, with recovery on crash.
"""
import uuid
import csv
import io
import json
import orjson
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.entities import AuditLog
from app.utils.crypto import hash_chain
from app.utils.redis_client import get_redis
from app.utils.distributed_lock import distributed_lock
from app.logging_config import get_logger

logger = get_logger("audit")
GENESIS_HASH = "0" * 64
BUFFER_KEY = "audit:buffer"
PROCESSING_KEY = "audit:processing"
MAX_BATCH = 200


class AuditService:

    @staticmethod
    async def log(
        agent_id: uuid.UUID,
        sponsor_id: uuid.UUID,
        action_type: str,
        service_name: str,
        permission_granted: bool,
        cost_usd: float = 0.0,
        prompt_snippet: str | None = None,
        model_used: str | None = None,
        policy_evaluation: dict | None = None,
        response_code: int | None = None,
        ip_address: str | None = None,
        duration_ms: int | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Push to Redis buffer. Returns entry dict."""
        entry = {
            "agent_id": str(agent_id),
            "sponsor_id": str(sponsor_id),
            "action_type": action_type,
            "service_name": service_name,
            "permission_granted": permission_granted,
            "cost_usd": cost_usd,
            "prompt_snippet": (prompt_snippet[:500] if prompt_snippet else None),
            "model_used": model_used,
            "policy_evaluation": policy_evaluation,
            "response_code": response_code,
            "ip_address": ip_address,
            "duration_ms": duration_ms,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            redis = await get_redis()
            await redis.rpush(BUFFER_KEY, orjson.dumps(entry).decode())
        except Exception as e:
            logger.error("audit_buffer_push_failed", error=str(e))
        return entry

    @staticmethod
    async def flush_buffer(db: AsyncSession) -> int:
        """
        Safe flush with processing list:
        1. Move entries: buffer → processing (atomic per entry)
        2. Process batch from processing list
        3. Clear processing list only after DB commit
        """
        redis = await get_redis()

        # Check if there's anything to process
        buf_len = await redis.llen(BUFFER_KEY)
        proc_len = await redis.llen(PROCESSING_KEY)

        if buf_len == 0 and proc_len == 0:
            return 0

        try:
            async with distributed_lock("audit:flush", ttl_seconds=15, retry_count=1):
                # Step 1: Move entries from buffer → processing
                if buf_len > 0:
                    for _ in range(min(buf_len, MAX_BATCH)):
                        entry = await redis.lmove(
                            BUFFER_KEY, PROCESSING_KEY, "LEFT", "RIGHT"
                        )
                        if entry is None:
                            break

                # Step 2: Read all from processing list
                raw_entries = await redis.lrange(PROCESSING_KEY, 0, -1)
                if not raw_entries:
                    return 0

                entries = []
                for raw in raw_entries:
                    try:
                        entries.append(orjson.loads(raw))
                    except json.JSONDecodeError:
                        logger.warning("audit_skip_malformed_entry")
                        continue

                if not entries:
                    await redis.delete(PROCESSING_KEY)
                    return 0

                # Step 3: Get last hash
                last_result = await db.execute(
                    select(AuditLog.log_hash).order_by(AuditLog.id.desc()).limit(1)
                )
                previous_hash = last_result.scalar_one_or_none() or GENESIS_HASH

                # Step 4: Build chain + insert
                db_objects = []
                for entry in entries:
                    log_data = json.dumps({
                        "agent_id": entry["agent_id"],
                        "sponsor_id": entry["sponsor_id"],
                        "action_type": entry["action_type"],
                        "service_name": entry["service_name"],
                        "permission_granted": entry["permission_granted"],
                        "cost_usd": entry["cost_usd"],
                        "timestamp": entry["timestamp"],
                    }, sort_keys=True)

                    log_hash = hash_chain(log_data, previous_hash)

                    ts = entry["timestamp"]
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)

                    db_objects.append(AuditLog(
                        log_hash=log_hash,
                        previous_hash=previous_hash,
                        agent_id=uuid.UUID(entry["agent_id"]),
                        sponsor_id=uuid.UUID(entry["sponsor_id"]),
                        action_type=entry["action_type"],
                        service_name=entry["service_name"],
                        prompt_snippet=entry.get("prompt_snippet"),
                        model_used=entry.get("model_used"),
                        permission_granted=entry["permission_granted"],
                        policy_evaluation=entry.get("policy_evaluation"),
                        cost_usd=entry["cost_usd"],
                        response_code=entry.get("response_code"),
                        ip_address=entry.get("ip_address"),
                        duration_ms=entry.get("duration_ms"),
                        audit_metadata=entry.get("metadata", {}),
                        timestamp=ts,
                    ))
                    previous_hash = log_hash

                db.add_all(db_objects)
                await db.commit()

                # Step 5: Clear processing ONLY after successful commit
                await redis.delete(PROCESSING_KEY)

                logger.info("audit_flushed", count=len(db_objects))
                return len(db_objects)

        except Exception as e:
            # On failure, entries remain in PROCESSING_KEY
            # and will be retried next flush cycle
            logger.error("audit_flush_error", error=str(e))
            return 0

    @staticmethod
    async def verify_chain_integrity(db: AsyncSession, limit: int = 1000) -> dict:
        result = await db.execute(
            select(AuditLog).order_by(AuditLog.id.asc()).limit(limit)
        )
        logs = list(result.scalars().all())
        if not logs:
            return {"valid": True, "checked": 0, "broken_at": []}
        broken = []
        for i, e in enumerate(logs):
            if i == 0:
                if e.previous_hash != GENESIS_HASH:
                    broken.append(e.id)
            elif e.previous_hash != logs[i - 1].log_hash:
                broken.append(e.id)
        return {"valid": len(broken) == 0, "checked": len(logs), "broken_at": broken}

    @staticmethod
    async def query(
        db: AsyncSession,
        sponsor_id: uuid.UUID,
        agent_id: uuid.UUID | None = None,
        service_name: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        q = select(AuditLog).where(AuditLog.sponsor_id == sponsor_id)
        if agent_id:
            q = q.where(AuditLog.agent_id == agent_id)
        if service_name:
            q = q.where(AuditLog.service_name == service_name)
        if since:
            q = q.where(AuditLog.timestamp >= since)
        q = q.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def count_recent(db: AsyncSession, agent_id: uuid.UUID, hours: int = 24) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.agent_id == agent_id,
                AuditLog.timestamp >= cutoff,
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def export_csv(db: AsyncSession, sponsor_id: uuid.UUID, since: datetime, until: datetime) -> str:
        logs = await db.execute(
            select(AuditLog).where(
                AuditLog.sponsor_id == sponsor_id,
                AuditLog.timestamp >= since,
                AuditLog.timestamp <= until,
            ).order_by(AuditLog.timestamp.asc()).limit(50000)
        )
        rows = list(logs.scalars().all())
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["id", "timestamp", "agent_id", "action_type", "service_name",
                     "granted", "cost_usd", "response_code", "hash"])
        for r in rows:
            w.writerow([r.id, r.timestamp.isoformat(), str(r.agent_id), r.action_type,
                        r.service_name, r.permission_granted, r.cost_usd, r.response_code, r.log_hash])
        return out.getvalue()