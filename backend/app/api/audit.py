import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.entities import User
from app.schemas.schemas import AuditLogOut
from app.services.audit_service import AuditService
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/logs", response_model=list[AuditLogOut])
async def get_audit_logs(
    agent_id: uuid.UUID | None = None,
    service_name: str | None = None,
    hours: int = Query(default=24, le=720),
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    logs = await AuditService.query(
        db, sponsor_id=user.id, agent_id=agent_id, service_name=service_name,
        since=since, limit=limit, offset=offset,
    )
    return logs


@router.get("/verify-chain")
async def verify_chain(
    limit: int = Query(default=1000, le=10000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await AuditService.verify_chain_integrity(db, limit=limit)