import pytest
import json
import uuid
from unittest.mock import patch, AsyncMock
from app.services.audit_service import AuditService


class TestAuditBuffer:
    @pytest.mark.asyncio
    async def test_log_pushes_to_redis(self, mock_redis):
        with patch("app.services.audit_service.get_redis", return_value=mock_redis):
            result = await AuditService.log(
                agent_id=uuid.uuid4(),
                sponsor_id=uuid.uuid4(),
                action_type="api_call",
                service_name="openai",
                permission_granted=True,
                cost_usd=0.05,
            )
            assert result["action_type"] == "api_call"
            assert result["cost_usd"] == 0.05
            assert result["permission_granted"] is True

    @pytest.mark.asyncio
    async def test_log_includes_timestamp(self, mock_redis):
        with patch("app.services.audit_service.get_redis", return_value=mock_redis):
            result = await AuditService.log(
                agent_id=uuid.uuid4(),
                sponsor_id=uuid.uuid4(),
                action_type="data_read",
                service_name="stripe",
                permission_granted=False,
            )
            assert "timestamp" in result
            assert "T" in result["timestamp"]  # ISO format

    @pytest.mark.asyncio
    async def test_prompt_truncated(self, mock_redis):
        long_prompt = "x" * 1000
        with patch("app.services.audit_service.get_redis", return_value=mock_redis):
            result = await AuditService.log(
                agent_id=uuid.uuid4(),
                sponsor_id=uuid.uuid4(),
                action_type="llm_inference",
                service_name="openai",
                permission_granted=True,
                prompt_snippet=long_prompt,
            )
            assert len(result["prompt_snippet"]) == 500