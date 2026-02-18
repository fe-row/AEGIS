import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.entities import User
from app.schemas.schemas import WalletOut, WalletTopUp, WalletConfig
from app.services.wallet_service import WalletService
from app.services.identity_service import IdentityService
from app.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/wallets", tags=["Wallets"])


@router.get("/{agent_id}", response_model=WalletOut)
async def get_wallet(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)
    wallet = await WalletService.get_wallet(db, agent_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


@router.post("/{agent_id}/top-up", response_model=WalletOut)
async def top_up_wallet(
    agent_id: uuid.UUID,
    data: WalletTopUp,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)
    wallet = await WalletService.top_up(db, agent_id, data.amount_usd)
    return wallet


@router.post("/{agent_id}/configure", response_model=WalletOut)
async def configure_wallet(
    agent_id: uuid.UUID,
    data: WalletConfig,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)
    wallet = await WalletService.get_wallet(db, agent_id)
    if not wallet:
        raise HTTPException(status_code=404)
    wallet.daily_limit_usd = data.daily_limit_usd
    wallet.monthly_limit_usd = data.monthly_limit_usd
    await db.commit()
    await db.refresh(wallet)
    return wallet


@router.post("/{agent_id}/freeze")
async def freeze_wallet(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent = await IdentityService.get_agent(db, agent_id)
    if not agent or agent.sponsor_id != user.id:
        raise HTTPException(status_code=404)
    await WalletService.freeze_wallet(db, agent_id)
    return {"status": "frozen"}