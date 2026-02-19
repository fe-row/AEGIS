import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.entities import User
from app.schemas.schemas import AuditLogOut
from app.services.audit_service import AuditService
from app.services.forensic_export import ForensicExportService
from app.middleware.auth_middleware import get_current_user
from app.services.rbac import require_permission

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/logs", response_model=list[AuditLogOut])
async def get_audit_logs(
    agent_id: uuid.UUID | None = None,
    service_name: str | None = None,
    hours: int = Query(default=24, le=720),
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
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
    user: User = Depends(require_permission("audit:read")),
):
    return await AuditService.verify_chain_integrity(db, limit=limit)


@router.get("/forensic/deep-verify")
async def deep_verify_chain(
    limit: int = Query(default=10000, le=100000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    """Full forensic verification — recomputes every hash from source data."""
    return await ForensicExportService.deep_verify_chain(db, limit=limit, offset=offset)


@router.post("/forensic/export")
async def forensic_export(
    from_id: int | None = Query(default=None),
    to_id: int | None = Query(default=None),
    batch_size: int = Query(default=10000, le=50000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("audit:admin")),
):
    """Export audit logs to immutable storage (S3 Object Lock / local)."""
    result = await ForensicExportService.export_batch(
        db, from_id=from_id, to_id=to_id,
        batch_size=batch_size, exported_by=user.email,
    )
    if not result.success and result.error:
        raise HTTPException(status_code=500, detail=result.error)
    return {
        "success": result.success,
        "record_count": result.record_count,
        "batch_hash": result.batch_hash,
        "storage_path": result.storage_path,
        "has_tsa": result.tsa_token is not None,
        "range": {"from_id": result.from_id, "to_id": result.to_id},
    }


@router.get("/forensic/report")
async def forensic_report(
    from_id: int = Query(..., ge=1),
    to_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    """Generate a forensic integrity report for an audit log range."""
    if to_id < from_id:
        raise HTTPException(status_code=400, detail="to_id must be >= from_id")
    return await ForensicExportService.generate_forensic_report(db, from_id, to_id)