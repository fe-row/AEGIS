"""Tests for AnomalyDetector — verifies detection logic and signature consistency."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.anomaly_detector import AnomalyDetector


def _make_profile(**overrides):
    defaults = {
        "typical_services": ["openai", "stripe"],
        "typical_hours": {"10": 5, "11": 3, "14": 8},
        "avg_requests_per_hour": 10.0,
        "avg_cost_per_action": 0.5,
    }
    defaults.update(overrides)
    profile = MagicMock()
    for k, v in defaults.items():
        setattr(profile, k, v)
    return profile


class TestDetectAnomaly:
    @pytest.mark.asyncio
    async def test_no_anomaly_when_no_profile(self):
        detector = AnomalyDetector()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await detector.detect_anomaly(db, "agent-1", "openai", "read")
        assert result["is_anomalous"] is False
        assert result["risk_score"] == 0.0

    @pytest.mark.asyncio
    async def test_unusual_service_flagged(self):
        detector = AnomalyDetector()
        profile = _make_profile()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = profile
        db.execute = AsyncMock(return_value=result_mock)

        with patch("app.services.anomaly_detector.get_redis") as mock_redis:
            redis = AsyncMock()
            redis.get = AsyncMock(return_value="0")
            mock_redis.return_value = redis

            result = await detector.detect_anomaly(db, "agent-1", "unknown_service", "read")
        assert "unusual_service:unknown_service" in result["anomalies"]
        assert result["risk_score"] >= 0.4


class TestRecordActionSignature:
    @pytest.mark.asyncio
    async def test_accepts_cost_parameter(self):
        """Ensures record_action accepts cost — matches proxy.py call signature."""
        detector = AnomalyDetector()
        with patch("app.services.anomaly_detector.get_redis") as mock_redis:
            redis = AsyncMock()
            mock_redis.return_value = redis
            # Should not raise TypeError
            await detector.record_action("agent-1", "openai", "inference", cost=0.05)
            assert redis.lpush.called

    @pytest.mark.asyncio
    async def test_cost_stored_in_entry(self):
        """Verifies cost value is included in the Redis entry."""
        import json
        detector = AnomalyDetector()
        with patch("app.services.anomaly_detector.get_redis") as mock_redis:
            redis = AsyncMock()
            mock_redis.return_value = redis
            await detector.record_action("agent-1", "openai", "inference", cost=0.123)
            call_args = redis.lpush.call_args
            entry = json.loads(call_args[0][1])
            assert entry["cost"] == 0.123
