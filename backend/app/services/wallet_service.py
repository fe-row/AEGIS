import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.entities import MicroWallet, WalletTransaction, ActionType


class WalletService:
    """Micro-Wallet management for per-agent FinOps."""

    @staticmethod
    async def get_wallet(db: AsyncSession, agent_id: uuid.UUID, *, for_update: bool = False) -> MicroWallet | None:
        stmt = select(MicroWallet).where(MicroWallet.agent_id == agent_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def check_and_reset_periods(db: AsyncSession, wallet: MicroWallet):
        now = datetime.now(timezone.utc)
        if wallet.last_reset_daily.date() < now.date():
            wallet.spent_today_usd = 0.0
            wallet.last_reset_daily = now
        if wallet.last_reset_monthly.month < now.month or wallet.last_reset_monthly.year < now.year:
            wallet.spent_this_month_usd = 0.0
            wallet.last_reset_monthly = now

    @staticmethod
    async def can_spend(db: AsyncSession, agent_id: uuid.UUID, amount: float) -> tuple[bool, str]:
        wallet = await WalletService.get_wallet(db, agent_id)
        if not wallet:
            return False, "No wallet found"
        if wallet.is_frozen:
            return False, "Wallet is frozen"

        await WalletService.check_and_reset_periods(db, wallet)

        if wallet.balance_usd < amount:
            return False, f"Insufficient balance: {wallet.balance_usd:.4f} < {amount:.4f}"
        if wallet.spent_today_usd + amount > wallet.daily_limit_usd:
            return False, f"Daily limit exceeded: {wallet.spent_today_usd:.2f} + {amount:.2f} > {wallet.daily_limit_usd:.2f}"
        if wallet.spent_this_month_usd + amount > wallet.monthly_limit_usd:
            return False, f"Monthly limit exceeded"
        return True, "OK"

    @staticmethod
    async def reserve_and_charge(
        db: AsyncSession,
        agent_id: uuid.UUID,
        amount: float,
        description: str,
        service_name: str,
        action_type: ActionType,
    ) -> tuple[bool, str, WalletTransaction | None]:
        """Atomic check + charge under FOR UPDATE to prevent race conditions."""
        wallet = await WalletService.get_wallet(db, agent_id, for_update=True)
        if not wallet:
            return False, "No wallet found", None
        if wallet.is_frozen:
            return False, "Wallet is frozen", None

        await WalletService.check_and_reset_periods(db, wallet)

        if wallet.balance_usd < amount:
            return False, f"Insufficient balance: {wallet.balance_usd:.4f} < {amount:.4f}", None
        if wallet.spent_today_usd + amount > wallet.daily_limit_usd:
            return False, f"Daily limit exceeded: {wallet.spent_today_usd:.2f} + {amount:.2f} > {wallet.daily_limit_usd:.2f}", None
        if wallet.spent_this_month_usd + amount > wallet.monthly_limit_usd:
            return False, "Monthly limit exceeded", None

        wallet.balance_usd -= amount
        wallet.spent_today_usd += amount
        wallet.spent_this_month_usd += amount

        tx = WalletTransaction(
            wallet_id=wallet.id,
            amount_usd=-amount,
            description=description,
            service_name=service_name,
            action_type=action_type,
        )
        db.add(tx)
        await db.commit()
        return True, "OK", tx

    @staticmethod
    async def charge(
        db: AsyncSession,
        agent_id: uuid.UUID,
        amount: float,
        description: str,
        service_name: str,
        action_type: ActionType,
    ) -> WalletTransaction | None:
        wallet = await WalletService.get_wallet(db, agent_id, for_update=True)
        if not wallet:
            return None

        await WalletService.check_and_reset_periods(db, wallet)

        wallet.balance_usd -= amount
        wallet.spent_today_usd += amount
        wallet.spent_this_month_usd += amount

        tx = WalletTransaction(
            wallet_id=wallet.id,
            amount_usd=-amount,
            description=description,
            service_name=service_name,
            action_type=action_type,
        )
        db.add(tx)
        await db.commit()
        return tx

    @staticmethod
    async def top_up(db: AsyncSession, agent_id: uuid.UUID, amount: float) -> MicroWallet:
        wallet = await WalletService.get_wallet(db, agent_id, for_update=True)
        if not wallet:
            raise ValueError(f"No wallet found for agent {agent_id}")
        wallet.balance_usd += amount
        tx = WalletTransaction(
            wallet_id=wallet.id,
            amount_usd=amount,
            description="Top-up",
            service_name="aegis_internal",
            action_type=ActionType.TRANSACTION,
        )
        db.add(tx)
        await db.commit()
        await db.refresh(wallet)
        return wallet

    @staticmethod
    async def freeze_wallet(db: AsyncSession, agent_id: uuid.UUID):
        wallet = await WalletService.get_wallet(db, agent_id)
        if wallet:
            wallet.is_frozen = True
            await db.commit()

    @staticmethod
    async def get_spend_in_window(
        db: AsyncSession,
        agent_id: uuid.UUID,
        window_seconds: int,
    ) -> float:
        wallet = await WalletService.get_wallet(db, agent_id)
        if not wallet:
            return 0.0
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        result = await db.execute(
            select(
                func.coalesce(func.sum(func.abs(WalletTransaction.amount_usd)), 0)
            ).where(
                WalletTransaction.wallet_id == wallet.id,
                WalletTransaction.timestamp >= cutoff,
                WalletTransaction.amount_usd < 0,
            )
        )
        return float(result.scalar())