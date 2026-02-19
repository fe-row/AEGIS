"""
Secrets Manager — Abstract interface for secrets providers.
Supports: environment variables (.env), HashiCorp Vault KV v2, AWS Secrets Manager.
"""
import os
import json
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("secrets_manager")
settings = get_settings()


class SecretsProvider(ABC):
    """Abstract base for secrets providers."""

    @abstractmethod
    async def get_secret(self, key: str) -> Optional[str]:
        ...

    @abstractmethod
    async def set_secret(self, key: str, value: str) -> bool:
        ...


class EnvSecretsProvider(SecretsProvider):
    """Read secrets from environment variables (default / current behavior)."""

    async def get_secret(self, key: str) -> Optional[str]:
        return os.environ.get(key)

    async def set_secret(self, key: str, value: str) -> bool:
        os.environ[key] = value
        return True


class VaultSecretsProvider(SecretsProvider):
    """Read/write secrets from HashiCorp Vault KV v2."""

    def __init__(self):
        self.addr = settings.VAULT_ADDR
        self.token = settings.VAULT_TOKEN
        self.path = settings.VAULT_SECRET_PATH

    async def get_secret(self, key: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.addr}/v1/{self.path}/data/{key}",
                    headers={"X-Vault-Token": self.token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("data", {}).get("data", {}).get("value")
                logger.warning("vault_get_failed", key=key, status=resp.status_code)
                return None
        except Exception as e:
            logger.error("vault_error", key=key, error=str(e))
            return None

    async def set_secret(self, key: str, value: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.addr}/v1/{self.path}/data/{key}",
                    headers={"X-Vault-Token": self.token},
                    json={"data": {"value": value}},
                )
                if resp.status_code in (200, 204):
                    logger.info("vault_secret_set", key=key)
                    return True
                logger.error("vault_set_failed", key=key, status=resp.status_code)
                return False
        except Exception as e:
            logger.error("vault_error", key=key, error=str(e))
            return False


class AWSSecretsProvider(SecretsProvider):
    """Read secrets from AWS Secrets Manager."""

    def __init__(self):
        self.secret_name = settings.AWS_SECRET_NAME

    async def get_secret(self, key: str) -> Optional[str]:
        try:
            import boto3
            client = boto3.client("secretsmanager")
            response = client.get_secret_value(SecretId=self.secret_name)
            secret_data = json.loads(response["SecretString"])
            return secret_data.get(key)
        except ImportError:
            logger.error("aws_boto3_missing", hint="Install boto3 for AWS Secrets Manager")
            return None
        except Exception as e:
            logger.error("aws_secrets_error", key=key, error=str(e))
            return None

    async def set_secret(self, key: str, value: str) -> bool:
        try:
            import boto3
            client = boto3.client("secretsmanager")
            # Get current secret, update key, write back
            try:
                response = client.get_secret_value(SecretId=self.secret_name)
                secret_data = json.loads(response["SecretString"])
            except Exception:
                secret_data = {}

            secret_data[key] = value
            client.update_secret(
                SecretId=self.secret_name,
                SecretString=json.dumps(secret_data),
            )
            logger.info("aws_secret_set", key=key)
            return True
        except ImportError:
            logger.error("aws_boto3_missing")
            return False
        except Exception as e:
            logger.error("aws_secrets_error", key=key, error=str(e))
            return False


# ── Factory ──

_provider: Optional[SecretsProvider] = None


def get_secrets_provider() -> SecretsProvider:
    """Get the configured secrets provider (singleton)."""
    global _provider
    if _provider is None:
        provider_type = settings.SECRETS_PROVIDER.lower()
        if provider_type == "vault":
            _provider = VaultSecretsProvider()
            logger.info("secrets_provider_initialized", type="vault")
        elif provider_type == "aws":
            _provider = AWSSecretsProvider()
            logger.info("secrets_provider_initialized", type="aws")
        else:
            _provider = EnvSecretsProvider()
            logger.info("secrets_provider_initialized", type="env")
    return _provider
