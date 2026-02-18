import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import Agent, AgentStatus, BehaviorProfile, MicroWallet
from app.schemas.schemas import AgentCreate, WalletConfig
from app.utils.crypto import generate_identity_fingerprint
from app.config import get_settings

settings = get_settings()


class IdentityService:
    """Synthetic Identity Provider for Non-Human Identities (NHI)."""

    @staticmethod
    async def register_agent(
        db: AsyncSession,
        sponsor_id: uuid.UUID,
        data: AgentCreate,
    ) -> Agent:
        fingerprint = generate_identity_fingerprint(data.name, str(sponsor_id))

        agent = Agent(
            sponsor_id=sponsor_id,
            name=data.name,
            description=data.description or "",
            agent_type=data.agent_type,
            status=AgentStatus.ACTIVE,
            trust_score=settings.INITIAL_TRUST_SCORE,
            identity_fingerprint=fingerprint,
            metadata_=data.metadata_ or {},
        )
        db.add(agent)
        await db.flush()

        # Create default wallet
        wallet = MicroWallet(
            agent_id=agent.id,
            balance_usd=0.0,
            daily_limit_usd=10.0,
            monthly_limit_usd=200.0,
        )
        db.add(wallet)

        # Create behavior profile
        profile = BehaviorProfile(
            agent_id=agent.id,
            typical_services=[],
            typical_hours={},
        )
        db.add(profile)

        await db.commit()
        await db.refresh(agent)
        return agent

    @staticmethod
    async def get_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_agent_for_sponsor(
        db: AsyncSession, agent_id: uuid.UUID, sponsor_id: uuid.UUID
    ) -> Agent | None:
        """Get agent only if it belongs to the given sponsor."""
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.sponsor_id == sponsor_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_agents(db: AsyncSession, sponsor_id: uuid.UUID) -> list[Agent]:
        result = await db.execute(
            select(Agent).where(Agent.sponsor_id == sponsor_id).order_by(Agent.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def suspend_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
        agent = await IdentityService.get_agent(db, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        agent.status = AgentStatus.SUSPENDED
        await db.commit()
        await db.refresh(agent)
        return agent

    @staticmethod
    async def activate_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
        agent = await IdentityService.get_agent(db, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        agent.status = AgentStatus.ACTIVE
        await db.commit()
        await db.refresh(agent)
        return agent

    @staticmethod
    async def panic_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
        agent = await IdentityService.get_agent(db, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        agent.status = AgentStatus.PANIC
        await db.commit()
        await db.refresh(agent)
        return agent