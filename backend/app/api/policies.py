import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import get_db
from app.models.entities import User, HITLRequest, HITLStatus
from app.schemas.schemas import HITLDecision, HITLOut
from app.services.hitl_gateway import HITLGateway
from app.middleware.auth_middleware import get_current_user
from app.services.rbac import require_permission

router = APIRouter(prefix="/policies", tags=["Policies & HITL"])


@router.get("/hitl/pending", response_model=list[HITLOut])
async def list_pending_hitl(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("policies:read")),
):
    return await HITLGateway.list_pending(db, user.id)


@router.post("/hitl/{request_id}/decide", response_model=HITLOut)
async def decide_hitl(
    request_id: uuid.UUID,
    data: HITLDecision,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("hitl:decide")),
):
    result = await HITLGateway.decide(db, request_id, user.id, data.approved, data.note)
    if not result:
        raise HTTPException(status_code=404, detail="HITL request not found")
    return result