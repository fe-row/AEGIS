"""Tests for WalletService — covers period resets, spend guards, and top_up safety."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.wallet_service import WalletService


def _make_wallet(**overrides):
    """Create a mock wallet with sensible defaults."""
    defaults = {
        "id": "wallet-1",
        "agent_id": "agent-1",
        "balance_usd": 100.0,
        "daily_limit_usd": 10.0,
        "monthly_limit_usd": 200.0,
        "spent_today_usd": 0.0,
        "spent_this_month_usd": 0.0,
        "last_reset_daily": datetime.now(timezone.utc),
        "last_reset_monthly": datetime.now(timezone.utc),
        "is_frozen": False,
    }
    defaults.update(overrides)
    wallet = MagicMock()
    for k, v in defaults.items():
        setattr(wallet, k, v)
    return wallet


class TestCanSpend:
    @pytest.mark.asyncio
    async def test_ok_when_within_limits(self):
        wallet = _make_wallet(balance_usd=50.0, spent_today_usd=0.0)
        db = AsyncMock()
        with patch.object(WalletService, "get_wallet", return_value=wallet):
            ok, msg = await WalletService.can_spend(db, "agent-1", 5.0)
        assert ok is True
        assert msg == "OK"

    @pytest.mark.asyncio
    async def test_fails_when_no_wallet(self):
        db = AsyncMock()
        with patch.object(WalletService, "get_wallet", return_value=None):
            ok, msg = await WalletService.can_spend(db, "agent-1", 1.0)
        assert ok is False
        assert "No wallet found" in msg

    @pytest.mark.asyncio
    async def test_fails_when_frozen(self):
        wallet = _make_wallet(is_frozen=True)
        db = AsyncMock()
        with patch.object(WalletService, "get_wallet", return_value=wallet):
            ok, msg = await WalletService.can_spend(db, "agent-1", 1.0)
        assert ok is False
        assert "frozen" in msg.lower()

    @pytest.mark.asyncio
    async def test_fails_when_insufficient_balance(self):
        wallet = _make_wallet(balance_usd=1.0)
        db = AsyncMock()
        with patch.object(WalletService, "get_wallet", return_value=wallet):
            ok, msg = await WalletService.can_spend(db, "agent-1", 5.0)
        assert ok is False
        assert "Insufficient" in msg

    @pytest.mark.asyncio
    async def test_fails_when_daily_limit_exceeded(self):
        wallet = _make_wallet(balance_usd=100.0, spent_today_usd=9.0, daily_limit_usd=10.0)
        db = AsyncMock()
        with patch.object(WalletService, "get_wallet", return_value=wallet):
            ok, msg = await WalletService.can_spend(db, "agent-1", 2.0)
        assert ok is False
        assert "Daily" in msg

    @pytest.mark.asyncio
    async def test_fails_when_monthly_limit_exceeded(self):
        wallet = _make_wallet(
            balance_usd=1000.0, spent_this_month_usd=199.0, monthly_limit_usd=200.0
        )
        db = AsyncMock()
        with patch.object(WalletService, "get_wallet", return_value=wallet):
            ok, msg = await WalletService.can_spend(db, "agent-1", 5.0)
        assert ok is False
        assert "Monthly" in msg


class TestPeriodResets:
    @pytest.mark.asyncio
    async def test_daily_reset_when_new_day(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        wallet = _make_wallet(spent_today_usd=50.0, last_reset_daily=yesterday)
        db = AsyncMock()
        await WalletService.check_and_reset_periods(db, wallet)
        assert wallet.spent_today_usd == 0.0

    @pytest.mark.asyncio
    async def test_monthly_reset_when_new_month(self):
        last_month = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
        wallet = _make_wallet(spent_this_month_usd=150.0, last_reset_monthly=last_month)
        db = AsyncMock()
        await WalletService.check_and_reset_periods(db, wallet)
        assert wallet.spent_this_month_usd == 0.0


class TestTopUpGuard:
    @pytest.mark.asyncio
    async def test_top_up_raises_when_no_wallet(self):
        db = AsyncMock()
        with patch.object(WalletService, "get_wallet", return_value=None):
            with pytest.raises(ValueError, match="No wallet found"):
                await WalletService.top_up(db, "agent-missing", 10.0)
