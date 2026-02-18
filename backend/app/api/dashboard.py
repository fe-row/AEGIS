"""Dashboard v4 — FIX: all queries run concurrently with asyncio.gather."""
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, extract, case
from app.models.database import get_db, AsyncSessionLocal
from app.models.entities import User, Agent, AgentStatus, AuditLog, HITLRequest, HITLStatus
from app.schemas.schemas import DashboardStats
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sid = user.id

    # Run all queries concurrently using separate sessions
    async def q_agents():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                select(
                    func.count(Agent.id),
                    func.count(case((Agent.status == AgentStatus.ACTIVE.value, 1))),
                    func.coalesce(func.avg(Agent.trust_score), 0),
                ).where(Agent.sponsor_id == sid)
            )
            return r.first()

    async def q_24h():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                select(
                    func.count(AuditLog.id),
                    func.count(case((AuditLog.permission_granted == False, 1))),
                    func.coalesce(func.sum(case((AuditLog.permission_granted == True, AuditLog.cost_usd), else_=0)), 0),
                ).where(AuditLog.sponsor_id == sid, AuditLog.timestamp >= day_ago)
            )
            return r.first()

    async def q_month():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                select(func.coalesce(func.sum(AuditLog.cost_usd), 0)).where(
                    AuditLog.sponsor_id == sid, AuditLog.timestamp >= month_start, AuditLog.permission_granted == True,
                )
            )
            return r.scalar() or 0

    async def q_hitl():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                select(func.count(HITLRequest.id)).where(
                    HITLRequest.sponsor_id == sid, HITLRequest.status == HITLStatus.PENDING.value,
                )
            )
            return r.scalar() or 0

    async def q_hourly():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                select(
                    extract("hour", AuditLog.timestamp).label("hr"),
                    func.coalesce(func.sum(case((AuditLog.permission_granted == True, AuditLog.cost_usd), else_=0)), 0),
                    func.count(case((AuditLog.permission_granted == False, 1))),
                ).where(AuditLog.sponsor_id == sid, AuditLog.timestamp >= day_ago)
                .group_by("hr").order_by("hr")
            )
            return {int(row[0]): {"spend": round(float(row[1]), 4), "blocked": int(row[2])} for row in r.fetchall()}

    async def q_services():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                select(
                    AuditLog.service_name,
                    func.count(AuditLog.id).label("cnt"),
                    func.coalesce(func.sum(AuditLog.cost_usd), 0),
                ).where(
                    AuditLog.sponsor_id == sid, AuditLog.timestamp >= day_ago, AuditLog.service_name.isnot(None),
                ).group_by(AuditLog.service_name).order_by(text("cnt DESC")).limit(10)
            )
            return [{"service": row[0], "requests": row[1], "cost": round(float(row[2]), 4)} for row in r.fetchall()]

    # Execute ALL concurrently
    agents_r, agg_r, month_r, hitl_r, hourly_r, services_r = await asyncio.gather(
        q_agents(), q_24h(), q_month(), q_hitl(), q_hourly(), q_services(),
    )

    total = agents_r[0] or 0
    active = agents_r[1] or 0
    avg_trust = float(agents_r[2] or 0)

    hourly_spend = [
        {"hour": f"{h:02d}:00", **hourly_r.get(h, {"spend": 0, "blocked": 0})}
        for h in range(24)
    ]

    return DashboardStats(
        total_agents=total,
        active_agents=active,
        suspended_agents=total - active,
        total_requests_24h=agg_r[0] or 0,
        total_blocked_24h=agg_r[1] or 0,
        total_spend_24h=round(float(agg_r[2] or 0), 4),
        total_spend_month=round(float(month_r), 4),
        avg_trust_score=round(avg_trust, 1),
        pending_hitl=hitl_r,
        circuit_breaker_triggers_24h=0,
        hourly_spend=hourly_spend,
        top_services=services_r,
    )