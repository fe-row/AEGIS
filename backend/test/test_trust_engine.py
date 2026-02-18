import pytest
from app.services.trust_engine import TrustEngine


class TestTrustEngine:
    def test_high_autonomy(self):
        result = TrustEngine.get_autonomy_level(90)
        assert result["level"] == "high"
        assert result["hitl_bypass"] is True
        assert result["spending_multiplier"] == 2.0
        assert result["max_cost_without_hitl"] == 10.0

    def test_medium_autonomy(self):
        result = TrustEngine.get_autonomy_level(65)
        assert result["level"] == "medium"
        assert result["hitl_bypass"] is False
        assert result["spending_multiplier"] == 1.5

    def test_standard_autonomy(self):
        result = TrustEngine.get_autonomy_level(50)
        assert result["level"] == "standard"
        assert result["spending_multiplier"] == 1.0

    def test_restricted_autonomy(self):
        result = TrustEngine.get_autonomy_level(25)
        assert result["level"] == "restricted"
        assert result["spending_multiplier"] == 0.5

    def test_quarantine(self):
        result = TrustEngine.get_autonomy_level(5)
        assert result["level"] == "quarantine"
        assert result["spending_multiplier"] == 0.0
        assert result["hitl_bypass"] is False
        assert result["max_cost_without_hitl"] == 0.0

    def test_boundary_80(self):
        assert TrustEngine.get_autonomy_level(80)["level"] == "high"
        assert TrustEngine.get_autonomy_level(79.9)["level"] == "medium"

    def test_boundary_0(self):
        assert TrustEngine.get_autonomy_level(0)["level"] == "quarantine"

    def test_boundary_100(self):
        assert TrustEngine.get_autonomy_level(100)["level"] == "high"


class TestTrustDeltas:
    def test_penalties_are_negative(self):
        assert TrustEngine.PENALTY_POLICY_VIOLATION < 0
        assert TrustEngine.PENALTY_ANOMALY < 0
        assert TrustEngine.PENALTY_CIRCUIT_BREAK < 0
        assert TrustEngine.PENALTY_PROMPT_INJECTION < 0
        assert TrustEngine.PENALTY_HITL_REJECTED < 0

    def test_rewards_are_positive(self):
        assert TrustEngine.REWARD_SUCCESS > 0
        assert TrustEngine.REWARD_CLEAN_STREAK > 0

    def test_circuit_break_is_severe(self):
        assert abs(TrustEngine.PENALTY_CIRCUIT_BREAK) > abs(TrustEngine.PENALTY_POLICY_VIOLATION)