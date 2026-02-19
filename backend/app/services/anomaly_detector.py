import uuid
from datetime import datetime, timezone
import orjson
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import BehaviorProfile
from app.config import get_settings
from app.utils.redis_client import get_redis

settings = get_settings()


class AnomalyDetector:
    """Behavioral anomaly detection for agents."""

    def __init__(self):
        pass

    async def record_action(self, agent_id: uuid.UUID, service_name: str, action: str, cost: float = 0.0):
        redis = await get_redis()
        now = datetime.now(timezone.utc)
        key = f"behavior:{agent_id}:actions"
        entry = orjson.dumps({
            "service": service_name,
            "action": action,
            "hour": now.hour,
            "ts": now.timestamp(),
            "cost": cost,
        }).decode()

        # Update hourly counter
        hour_key = f"behavior:{agent_id}:hour:{now.hour}"

        pipe = redis.pipeline()
        pipe.lpush(key, entry)
        pipe.ltrim(key, 0, 999)
        pipe.incr(hour_key)
        pipe.expire(hour_key, 7200)
        await pipe.execute()

    async def detect_anomaly(
        self,
        db: AsyncSession,
        agent_id: uuid.UUID,
        service_name: str,
        action: str,
    ) -> dict:
        result = await db.execute(
            select(BehaviorProfile).where(BehaviorProfile.agent_id == agent_id)
        )
        profile = result.scalar_one_or_none()

        anomalies = []
        risk_score = 0.0

        if not profile:
            return {"is_anomalous": False, "risk_score": 0.0, "anomalies": []}

        # Check 1: Service not in typical usage
        if profile.typical_services and service_name not in profile.typical_services:
            anomalies.append(f"unusual_service:{service_name}")
            risk_score += 0.4

        # Check 2: Unusual hour
        now_hour = str(datetime.now(timezone.utc).hour)
        if profile.typical_hours:
            typical_freq = profile.typical_hours.get(now_hour, 0)
            if typical_freq == 0:
                anomalies.append(f"unusual_hour:{now_hour}")
                risk_score += 0.3

        # Check 3: Request velocity
        redis = await get_redis()
        hour_key = f"behavior:{agent_id}:hour:{datetime.now(timezone.utc).hour}"
        current_count = int(await redis.get(hour_key) or 0)
        if profile.avg_requests_per_hour > 0 and current_count > profile.avg_requests_per_hour * 3:
            anomalies.append(f"velocity_spike:{current_count}")
            risk_score += 0.5

        is_anomalous = risk_score >= 0.6

        return {
            "is_anomalous": is_anomalous,
            "risk_score": min(risk_score, 1.0),
            "anomalies": anomalies,
        }

    async def update_profile(self, db: AsyncSession, agent_id: uuid.UUID):
        """Recalculate behavior profile from recent actions."""
        redis = await get_redis()
        key = f"behavior:{agent_id}:actions"
        raw = await redis.lrange(key, 0, 999)

        if not raw:
            return

        actions = [orjson.loads(r) for r in raw]

        services = list(set(a["service"] for a in actions))
        hours = {}
        for a in actions:
            h = str(a["hour"])
            hours[h] = hours.get(h, 0) + 1

        total_hours = len(set(a["hour"] for a in actions)) or 1
        avg_rpm = len(actions) / total_hours

        result = await db.execute(
            select(BehaviorProfile).where(BehaviorProfile.agent_id == agent_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            profile.typical_services = services
            profile.typical_hours = hours
            profile.avg_requests_per_hour = avg_rpm
            profile.last_updated = datetime.now(timezone.utc)
        else:
            profile = BehaviorProfile(
                agent_id=agent_id,
                typical_services=services,
                typical_hours=hours,
                avg_requests_per_hour=avg_rpm,
            )
            db.add(profile)
        await db.commit()


anomaly_detector = AnomalyDetector()