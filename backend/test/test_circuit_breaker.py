import pytest
from app.services.circuit_breaker import CircuitBreaker


class TestCircuitBreakerParsing:
    def test_sum_amounts_normal(self):
        entries = ["1700000000.123_0.05", "1700000001.456_0.10", "1700000002.789_0.25"]
        total = CircuitBreaker._sum_amounts(entries)
        assert abs(total - 0.40) < 0.001

    def test_sum_amounts_empty(self):
        assert CircuitBreaker._sum_amounts([]) == 0.0

    def test_sum_amounts_malformed(self):
        entries = ["garbage", "1700000000.123_0.05", "also_garbage_data"]
        total = CircuitBreaker._sum_amounts(entries)
        assert abs(total - 0.05) < 0.001

    def test_sum_amounts_large_values(self):
        entries = [f"1700000000.0_{i * 0.01}" for i in range(100)]
        total = CircuitBreaker._sum_amounts(entries)
        expected = sum(i * 0.01 for i in range(100))
        assert abs(total - expected) < 0.01

    def test_sum_amounts_negative(self):
        entries = ["1700000000.0_-0.05"]
        total = CircuitBreaker._sum_amounts(entries)
        assert total == -0.05

    def test_sum_amounts_underscore_in_timestamp(self):
        """Ensure rsplit handles edge case."""
        entries = ["1700_000_000.0_0.05"]  # Multiple underscores
        total = CircuitBreaker._sum_amounts(entries)
        assert abs(total - 0.05) < 0.001