import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import StateSnapshot


class RollbackService:
    """State Rollback — undo agent actions if they go wrong."""

    @staticmethod
    async def save_snapshot(
        db: AsyncSession,
        agent_id: uuid.UUID,
        audit_log_id: int,
        snapshot_data: dict,
        rollback_instructions: dict | None = None,
    ) -> StateSnapshot:
        snap = StateSnapshot(
            agent_id=agent_id,
            audit_log_id=audit_log_id,
            snapshot_data=snapshot_data,
            rollback_instructions=rollback_instructions or {},
        )
        db.add(snap)
        await db.commit()
        await db.refresh(snap)
        return snap

    @staticmethod
    async def get_snapshots(
        db: AsyncSession,
        agent_id: uuid.UUID,
        limit: int = 20,
    ) -> list[StateSnapshot]:
        result = await db.execute(
            select(StateSnapshot)
            .where(StateSnapshot.agent_id == agent_id)
            .order_by(StateSnapshot.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def execute_rollback(
        db: AsyncSession,
        snapshot_id: uuid.UUID,
    ) -> dict:
        result = await db.execute(
            select(StateSnapshot).where(StateSnapshot.id == snapshot_id)
        )
        snap = result.scalar_one_or_none()
        if not snap:
            return {"success": False, "error": "Snapshot not found"}
        if snap.is_rolled_back:
            return {"success": False, "error": "Already rolled back"}

        instructions = snap.rollback_instructions or {}

        # The actual rollback logic depends on the service.
        # Here we provide the framework; each integration implements the undo.
        rollback_result = {
            "snapshot_id": str(snap.id),
            "instructions": instructions,
            "snapshot_data": snap.snapshot_data,
            "action": "rollback_ready",
        }

        snap.is_rolled_back = True
        snap.rolled_back_at = datetime.now(timezone.utc)
        await db.commit()

        return {"success": True, "result": rollback_result}