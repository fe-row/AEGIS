import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import get_db
from app.models.entities import User, Agent, AgentPermission, SecretVault
from app.schemas.schemas import (
    AgentCreate, AgentOut, AgentDetail, PermissionCreate, PermissionOut, SecretStore,
)
from app.services.identity_service import IdentityService
from app.services.trust_engine import TrustEngine
from app.services.audit_service import AuditService
from app.utils.crypto import encrypt_secret
from app.utils.cache import invalidate_cached_permission
from app.middleware.auth_middleware import get_current_user
from app.services.rbac import require_permission

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post("/", response_model=AgentOut, status_code=201)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:write")),
):
    agent = await IdentityService.register_agent(db, user.id, data)
    return agent


@router.get("/", response_model=list[AgentOut])
async def list_agents(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:read")),
):
    return await IdentityService.list_agents(db, user.id, limit=limit, offset=offset)


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:read")),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    wallet = agent.wallet
    perms = await db.execute(
        select(AgentPermission).where(
            AgentPermission.agent_id == agent_id,
            AgentPermission.is_active == True,
        )
    )
    active_perms = len(list(perms.scalars().all()))
    actions_24h = await AuditService.count_recent(db, agent_id, hours=24)

    return AgentDetail(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type,
        status=agent.status,
        trust_score=agent.trust_score,
        identity_fingerprint=agent.identity_fingerprint,
        created_at=agent.created_at,
        wallet_balance=wallet.balance_usd if wallet else None,
        active_permissions=active_perms,
        total_actions_24h=actions_24h,
    )


@router.post("/{agent_id}/suspend")
async def suspend_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:write")),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)
    await IdentityService.suspend_agent(db, agent_id)
    return {"status": "suspended"}


@router.post("/{agent_id}/activate")
async def activate_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:write")),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)
    await IdentityService.activate_agent(db, agent_id)
    return {"status": "active"}


# ── Permissions ──

@router.post("/{agent_id}/permissions", response_model=PermissionOut, status_code=201)
async def add_permission(
    agent_id: uuid.UUID,
    data: PermissionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:write")),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)

    perm = AgentPermission(
        agent_id=agent_id,
        service_name=data.service_name,
        allowed_actions=data.allowed_actions,
        max_requests_per_hour=data.max_requests_per_hour,
        time_window_start=data.time_window_start,
        time_window_end=data.time_window_end,
        max_records_per_request=data.max_records_per_request,
        requires_hitl=data.requires_hitl,
        custom_policy=data.custom_policy,
    )
    db.add(perm)
    await db.commit()
    await db.refresh(perm)
    await invalidate_cached_permission(agent_id, data.service_name)
    return perm


@router.get("/{agent_id}/permissions", response_model=list[PermissionOut])
async def list_permissions(
    agent_id: uuid.UUID,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:read")),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)

    result = await db.execute(
        select(AgentPermission)
        .where(AgentPermission.agent_id == agent_id)
        .order_by(AgentPermission.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.delete("/{agent_id}/permissions/{perm_id}", status_code=204)
async def delete_permission(
    agent_id: uuid.UUID,
    perm_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("agents:delete")),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)

    result = await db.execute(
        select(AgentPermission).where(
            AgentPermission.id == perm_id,
            AgentPermission.agent_id == agent_id,
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    await db.delete(perm)
    await db.commit()
    await invalidate_cached_permission(agent_id, perm.service_name)


# ── Secrets Vault ──

@router.post("/{agent_id}/secrets", status_code=201)
async def store_secret(
    agent_id: uuid.UUID,
    data: SecretStore,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("secrets:write")),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)

    encrypted = encrypt_secret(data.secret_value)

    # Upsert
    result = await db.execute(
        select(SecretVault).where(
            SecretVault.sponsor_id == user.id,
            SecretVault.service_name == data.service_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.encrypted_secret = encrypted
        existing.secret_type = data.secret_type
        existing.rotation_interval_hours = data.rotation_interval_hours
    else:
        vault = SecretVault(
            sponsor_id=user.id,
            service_name=data.service_name,
            encrypted_secret=encrypted,
            secret_type=data.secret_type,
            rotation_interval_hours=data.rotation_interval_hours,
        )
        db.add(vault)

    await db.commit()
    return {"status": "stored", "service_name": data.service_name}