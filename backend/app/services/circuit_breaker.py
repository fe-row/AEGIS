import uuid
from datetime import datetime, timezone
from app.config import get_settings
from app.utils.redis_client import get_redis
from app.services.wallet_service import WalletService
from app.services.identity_service import IdentityService
from app.services.jit_broker import jit_broker

settings = get_settings()


class CircuitBreaker:
    """Monitors spending velocity and triggers panic mode."""

    def __init__(self):
        self.window = settings.CIRCUIT_BREAKER_WINDOW_SECONDS
        self.threshold_pct = settings.CIRCUIT_BREAKER_THRESHOLD_PCT

    @staticmethod
    def _sum_amounts(entries: list[str]) -> float:
        """Parse '{timestamp}|{amount}' entries and sum amounts."""
        total = 0.0
        for e in entries:
            try:
                _, amt = e.rsplit("|", 1)
                total += float(amt)
            except (ValueError, IndexError):
                continue
        return total

    async def record_spend(self, agent_id: uuid.UUID, amount: float):
        redis = await get_redis()
        key = f"cb:spend:{agent_id}"
        now = datetime.now(timezone.utc).timestamp()
        await redis.zadd(key, {f"{now}|{amount}": now})
        await redis.zremrangebyscore(key, 0, now - self.window * 2)

    async def check_and_trip(self, db, agent_id: uuid.UUID, amount: float) -> bool:
        redis = await get_redis()
        key = f"cb:spend:{agent_id}"
        now = datetime.now(timezone.utc).timestamp()

        # Current window spend
        current_entries = await redis.zrangebyscore(
            key, now - self.window, now
        )
        current_total = self._sum_amounts(current_entries) + amount

        # Previous window spend (baseline)
        previous_entries = await redis.zrangebyscore(
            key, now - self.window * 2, now - self.window
        )
        previous_total = self._sum_amounts(previous_entries)

        if previous_total > 0:
            increase_pct = ((current_total - previous_total) / previous_total) * 100
            if increase_pct >= self.threshold_pct:
                await self._trigger_panic(db, agent_id)
                return True

        # Also trip if absolute spend in window is abnormally high
        baseline_key = f"cb:baseline:{agent_id}"
        baseline = await redis.get(baseline_key)
        if baseline:
            baseline_val = float(baseline)
            if baseline_val > 0 and current_total > baseline_val * 4:
                await self._trigger_panic(db, agent_id)
                return True

        return False

    async def _trigger_panic(self, db, agent_id: uuid.UUID):
        """Full panic mode: revoke everything."""
        redis = await get_redis()
        await IdentityService.panic_agent(db, agent_id)
        await jit_broker.revoke_all_for_agent(agent_id)
        await WalletService.freeze_wallet(db, agent_id)

        # Record the trip event
        trip_key = f"cb:trips:{agent_id}"
        await redis.lpush(trip_key, datetime.now(timezone.utc).isoformat())
        await redis.ltrim(trip_key, 0, 99)

    async def update_baseline(self, agent_id: uuid.UUID, avg_spend: float):
        redis = await get_redis()
        key = f"cb:baseline:{agent_id}"
        await redis.set(key, str(avg_spend))


circuit_breaker = CircuitBreaker()