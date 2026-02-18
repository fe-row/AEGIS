import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import Agent
from app.config import get_settings

settings = get_settings()


class TrustEngine:
    """Agent reputation system. Good behavior → more autonomy."""

    REWARD_SUCCESSFUL_ACTION = 0.1
    REWARD_CLEAN_AUDIT = 0.5
    PENALTY_POLICY_VIOLATION = -2.0
    PENALTY_ANOMALY = -5.0
    PENALTY_CIRCUIT_BREAK = -15.0
    PENALTY_PROMPT_INJECTION = -10.0
    PENALTY_HITL_REJECTED = -3.0

    # Aliases used by tests / external callers
    REWARD_SUCCESS = REWARD_SUCCESSFUL_ACTION
    REWARD_CLEAN_STREAK = REWARD_CLEAN_AUDIT

    @staticmethod
    async def adjust_score(
        db: AsyncSession,
        agent_id: uuid.UUID,
        delta: float,
        reason: str,
    ) -> float:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        new_score = agent.trust_score + delta
        new_score = max(settings.MIN_TRUST_SCORE, min(settings.MAX_TRUST_SCORE, new_score))
        agent.trust_score = new_score
        await db.commit()
        return new_score

    @staticmethod
    async def reward_success(db: AsyncSession, agent_id: uuid.UUID) -> float:
        return await TrustEngine.adjust_score(
            db, agent_id, TrustEngine.REWARD_SUCCESSFUL_ACTION, "successful_action"
        )

    @staticmethod
    async def penalize_violation(db: AsyncSession, agent_id: uuid.UUID) -> float:
        return await TrustEngine.adjust_score(
            db, agent_id, TrustEngine.PENALTY_POLICY_VIOLATION, "policy_violation"
        )

    @staticmethod
    async def penalize_anomaly(db: AsyncSession, agent_id: uuid.UUID) -> float:
        return await TrustEngine.adjust_score(
            db, agent_id, TrustEngine.PENALTY_ANOMALY, "anomaly_detected"
        )

    @staticmethod
    async def penalize_circuit_break(db: AsyncSession, agent_id: uuid.UUID) -> float:
        return await TrustEngine.adjust_score(
            db, agent_id, TrustEngine.PENALTY_CIRCUIT_BREAK, "circuit_breaker_tripped"
        )

    @staticmethod
    async def penalize_injection(db: AsyncSession, agent_id: uuid.UUID) -> float:
        return await TrustEngine.adjust_score(
            db, agent_id, TrustEngine.PENALTY_PROMPT_INJECTION, "prompt_injection_detected"
        )

    @staticmethod
    def get_autonomy_level(trust_score: float) -> dict:
        """Higher trust = higher limits."""
        if trust_score >= 80:
            return {"level": "high", "spending_multiplier": 2.0, "hitl_bypass": True, "max_cost_without_hitl": 10.0}
        elif trust_score >= 60:
            return {"level": "medium", "spending_multiplier": 1.5, "hitl_bypass": False, "max_cost_without_hitl": 5.0}
        elif trust_score >= 40:
            return {"level": "standard", "spending_multiplier": 1.0, "hitl_bypass": False, "max_cost_without_hitl": 2.0}
        elif trust_score >= 20:
            return {"level": "restricted", "spending_multiplier": 0.5, "hitl_bypass": False, "max_cost_without_hitl": 0.5}
        else:
            return {"level": "quarantine", "spending_multiplier": 0.0, "hitl_bypass": False, "max_cost_without_hitl": 0.0}