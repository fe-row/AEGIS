"""
Tests for MFA, RBAC, and Alerting services.
"""
import pytest
import secrets
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.services.mfa import MFAService


# ══════════════════════════════════════════════════
#  MFA Tests
# ══════════════════════════════════════════════════

class TestMFAService:
    """Tests for TOTP MFA service."""

    def test_generate_secret(self):
        secret = MFAService.generate_secret()
        assert len(secret) == 32  # Base32 encoded
        assert secret.isalnum()

    def test_provisioning_uri(self):
        secret = MFAService.generate_secret()
        uri = MFAService.get_provisioning_uri(secret, "user@example.com")
        assert "otpauth://totp/" in uri
        assert "user@example.com" in uri
        assert "AEGIS" in uri
        assert secret in uri

    def test_verify_code_valid(self):
        import pyotp
        secret = MFAService.generate_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert MFAService.verify_code(secret, code) is True

    def test_verify_code_invalid(self):
        secret = MFAService.generate_secret()
        assert MFAService.verify_code(secret, "000000") is False

    def test_generate_backup_codes(self):
        codes = MFAService.generate_backup_codes(count=8)
        assert len(codes) == 8
        for code in codes:
            assert len(code) == 10  # 8 hex chars + 1 dash
            assert "-" in code
        # All unique
        assert len(set(codes)) == 8

    def test_hash_and_verify_backup_code(self):
        code = "abcd-efgh"
        hashed = MFAService.hash_backup_code(code)
        assert hashed != code
        # Verify against list
        hashed_list = [MFAService.hash_backup_code("xxxx-yyyy"), hashed]
        idx = MFAService.verify_backup_code(code, hashed_list)
        assert idx == 1

    def test_verify_backup_code_invalid(self):
        hashed_list = [MFAService.hash_backup_code("abcd-efgh")]
        idx = MFAService.verify_backup_code("wrong-code", hashed_list)
        assert idx is None


# ══════════════════════════════════════════════════
#  RBAC Tests
# ══════════════════════════════════════════════════

class TestRBACService:
    """Tests for RBAC permission checks."""

    @pytest.mark.asyncio
    async def test_superadmin_has_all_permissions(self):
        from app.services.rbac import RBACService
        from app.models.entities import UserRole

        user = MagicMock()
        user.is_superadmin = True
        user.role = UserRole.VIEWER

        perms = await RBACService.get_user_permissions(user)
        assert "*" in perms

    @pytest.mark.asyncio
    async def test_superadmin_check_any_permission(self):
        from app.services.rbac import RBACService

        user = MagicMock()
        user.is_superadmin = True

        result = await RBACService.check_permission(user, "anything:at_all")
        assert result is True

    @pytest.mark.asyncio
    async def test_viewer_cannot_write(self):
        from app.services.rbac import RBACService
        from app.models.entities import UserRole

        user = MagicMock()
        user.is_superadmin = False
        user.role = UserRole.VIEWER

        result = await RBACService.check_permission(user, "agents:write")
        assert result is False

    @pytest.mark.asyncio
    async def test_viewer_can_read(self):
        from app.services.rbac import RBACService
        from app.models.entities import UserRole

        user = MagicMock()
        user.is_superadmin = False
        user.role = UserRole.VIEWER

        result = await RBACService.check_permission(user, "agents:read")
        assert result is True

    @pytest.mark.asyncio
    async def test_admin_has_broad_permissions(self):
        from app.services.rbac import RBACService
        from app.models.entities import UserRole

        user = MagicMock()
        user.is_superadmin = False
        user.role = UserRole.ADMIN

        for perm in ["agents:read", "agents:write", "wallets:read", "audit:read", "users:write"]:
            assert await RBACService.check_permission(user, perm), f"Admin should have {perm}"

    @pytest.mark.asyncio
    async def test_finance_auditor_limited_scope(self):
        from app.services.rbac import RBACService
        from app.models.entities import UserRole

        user = MagicMock()
        user.is_superadmin = False
        user.role = UserRole.FINANCE_AUDITOR

        assert await RBACService.check_permission(user, "wallets:read") is True
        assert await RBACService.check_permission(user, "audit:read") is True
        assert await RBACService.check_permission(user, "agents:write") is False


# ══════════════════════════════════════════════════
#  Alerting Tests
# ══════════════════════════════════════════════════

class TestAlertService:
    """Tests for alerting service."""

    @pytest.mark.asyncio
    async def test_pagerduty_sends_event(self):
        from app.services.alerting import AlertService, AlertSeverity

        with patch("app.services.alerting.settings") as mock_settings, \
             patch("httpx.AsyncClient") as mock_client_cls:

            mock_settings.ALERT_PROVIDER = "pagerduty"
            mock_settings.PAGERDUTY_ROUTING_KEY = "test-routing-key"
            mock_settings.OPSGENIE_API_KEY = ""

            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_resp
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_instance

            await AlertService.send_alert("Test alert", AlertSeverity.ERROR)

            mock_client_instance.post.assert_called_once()
            call_args = mock_client_instance.post.call_args
            assert "pagerduty.com" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_no_provider_logs_warning(self):
        from app.services.alerting import AlertService

        with patch("app.services.alerting.settings") as mock_settings, \
             patch("app.services.alerting.logger") as mock_logger:

            mock_settings.ALERT_PROVIDER = ""
            mock_settings.PAGERDUTY_ROUTING_KEY = ""
            mock_settings.OPSGENIE_API_KEY = ""

            await AlertService.send_alert("Test alert")

            mock_logger.warning.assert_called_once_with(
                "alert_no_provider", summary="Test alert"
            )


# ══════════════════════════════════════════════════
#  Secrets Manager Tests
# ══════════════════════════════════════════════════

class TestSecretsManager:
    """Tests for secrets provider factory."""

    @pytest.mark.asyncio
    async def test_env_provider_reads_env(self):
        import os
        from app.utils.secrets_manager import EnvSecretsProvider

        os.environ["TEST_SECRET_KEY"] = "secret_value"
        provider = EnvSecretsProvider()
        val = await provider.get_secret("TEST_SECRET_KEY")
        assert val == "secret_value"
        del os.environ["TEST_SECRET_KEY"]

    @pytest.mark.asyncio
    async def test_env_provider_returns_none_for_missing(self):
        from app.utils.secrets_manager import EnvSecretsProvider

        provider = EnvSecretsProvider()
        val = await provider.get_secret("NONEXISTENT_KEY_12345")
        assert val is None

    def test_factory_returns_env_by_default(self):
        from app.utils.secrets_manager import get_secrets_provider, EnvSecretsProvider
        import app.utils.secrets_manager as sm

        sm._provider = None  # Reset singleton
        with patch("app.utils.secrets_manager.settings") as mock_settings:
            mock_settings.SECRETS_PROVIDER = "env"
            provider = get_secrets_provider()
            assert isinstance(provider, EnvSecretsProvider)
        sm._provider = None  # Clean up
