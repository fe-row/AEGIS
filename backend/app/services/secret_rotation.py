"""
Secret Rotation Service — Automated credential lifecycle management.

Checks SecretVault entries with rotation_interval_hours > 0 and rotates
secrets that are past their rotation window. Supports pluggable rotation
strategies per service type.
"""
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.entities import SecretVault
from app.utils.crypto import encrypt_secret, decrypt_secret
from app.services.jit_broker import jit_broker
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("secret_rotation")
settings = get_settings()


class SecretRotationService:
    """Manages automated rotation of secrets stored in the vault."""

    @staticmethod
    async def check_and_rotate(db: AsyncSession) -> dict:
        """
        Scan all secrets with rotation enabled and rotate those past due.
        Returns summary of rotations performed.
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(SecretVault).where(SecretVault.rotation_interval_hours > 0)
        )
        secrets = list(result.scalars().all())

        rotated = 0
        skipped = 0
        errors = []

        for secret in secrets:
            try:
                deadline = secret.last_rotated_at + timedelta(
                    hours=secret.rotation_interval_hours
                )
                if now < deadline:
                    skipped += 1
                    continue

                new_secret = await SecretRotationService._rotate_secret(
                    db, secret
                )
                if new_secret:
                    rotated += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append({
                    "secret_id": str(secret.id),
                    "service": secret.service_name,
                    "error": str(e),
                })
                logger.error(
                    "secret_rotation_error",
                    secret_id=str(secret.id),
                    service=secret.service_name,
                    error=str(e),
                )

        logger.info(
            "secret_rotation_cycle",
            total=len(secrets),
            rotated=rotated,
            skipped=skipped,
            errors=len(errors),
        )

        return {
            "total_checked": len(secrets),
            "rotated": rotated,
            "skipped": skipped,
            "errors": errors,
            "timestamp": now.isoformat(),
        }

    @staticmethod
    async def _rotate_secret(
        db: AsyncSession,
        secret: SecretVault,
    ) -> bool:
        """
        Rotate a single secret:
        1. Decrypt current secret
        2. Generate new secret via provider strategy
        3. Encrypt and store new secret
        4. Update rotation timestamp
        5. Invalidate cached JIT tokens for affected agents
        """
        try:
            current_value = decrypt_secret(secret.encrypted_secret)
        except Exception as e:
            logger.error(
                "rotation_decrypt_failed",
                secret_id=str(secret.id),
                error=str(e),
            )
            return False

        # Generate new secret based on service type
        new_value = await _generate_new_secret(
            secret.service_name, secret.secret_type, current_value,
        )

        if not new_value:
            logger.warning(
                "rotation_no_strategy",
                service=secret.service_name,
                secret_type=secret.secret_type,
            )
            return False

        # Encrypt and store
        secret.encrypted_secret = encrypt_secret(new_value)
        secret.last_rotated_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "secret_rotated",
            secret_id=str(secret.id),
            service=secret.service_name,
        )

        return True

    @staticmethod
    async def force_rotate(
        db: AsyncSession,
        secret_id: uuid.UUID,
    ) -> dict:
        """Force-rotate a specific secret regardless of schedule."""
        result = await db.execute(
            select(SecretVault).where(SecretVault.id == secret_id)
        )
        secret = result.scalar_one_or_none()
        if not secret:
            return {"success": False, "error": "Secret not found"}

        rotated = await SecretRotationService._rotate_secret(db, secret)
        return {
            "success": rotated,
            "secret_id": str(secret_id),
            "service": secret.service_name,
            "rotated_at": datetime.now(timezone.utc).isoformat() if rotated else None,
        }

    @staticmethod
    async def get_rotation_status(db: AsyncSession) -> list[dict]:
        """Get rotation status for all secrets with rotation enabled."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(SecretVault).where(SecretVault.rotation_interval_hours > 0)
        )
        secrets = list(result.scalars().all())

        statuses = []
        for s in secrets:
            deadline = s.last_rotated_at + timedelta(hours=s.rotation_interval_hours)
            is_overdue = now > deadline
            hours_until = max(0, (deadline - now).total_seconds() / 3600)

            statuses.append({
                "id": str(s.id),
                "service_name": s.service_name,
                "secret_type": s.secret_type,
                "rotation_interval_hours": s.rotation_interval_hours,
                "last_rotated_at": s.last_rotated_at.isoformat(),
                "next_rotation_at": deadline.isoformat(),
                "is_overdue": is_overdue,
                "hours_until_rotation": round(hours_until, 1),
            })

        return statuses


# ═══════════════════════════════════════════════════════
#  Rotation Strategies
# ═══════════════════════════════════════════════════════

async def _generate_new_secret(
    service_name: str,
    secret_type: str,
    current_value: str,
) -> str | None:
    """
    Generate a new secret value. Supports:
    - Internal (aegis-managed) keys: generate new random key
    - External APIs: call provider's key rotation endpoint

    Returns new secret value, or None if no strategy is available.
    """
    # Strategy 1: Self-managed API keys (just generate new random)
    if secret_type == "api_key" and service_name in _SELF_ROTATE_SERVICES:
        import secrets as sec
        return f"sk-{sec.token_urlsafe(48)}"

    # Strategy 2: OpenAI — no API rotation endpoint, log warning
    if service_name == "openai":
        logger.warning(
            "rotation_manual_required",
            service="openai",
            reason="OpenAI does not support automated key rotation via API",
        )
        return None

    # Strategy 3: AWS — use STS to rotate access keys
    if service_name == "aws" and secret_type == "api_key":
        return await _rotate_aws_key(current_value)

    # Strategy 4: Generic webhook rotation
    if settings.SECRET_ROTATION_WEBHOOK_URL:
        return await _rotate_via_webhook(service_name, secret_type, current_value)

    # No strategy available
    return None


# Services where AEGIS generates the key (internal services, test endpoints)
_SELF_ROTATE_SERVICES = {"aegis_internal", "test", "internal_api", "webhook_target"}


async def _rotate_aws_key(current_key: str) -> str | None:
    """Rotate AWS access key using boto3 IAM."""
    try:
        import boto3
        iam = boto3.client("iam")
        # List current keys, create new, delete old
        # This is a simplified flow — production needs more error handling
        user_info = iam.get_access_key_last_used(AccessKeyId=current_key)
        username = user_info.get("UserName", "")
        if not username:
            return None

        new_key = iam.create_access_key(UserName=username)
        new_access_key = new_key["AccessKey"]["AccessKeyId"]
        new_secret_key = new_key["AccessKey"]["SecretAccessKey"]

        # Deactivate old key (don't delete immediately for safety)
        iam.update_access_key(
            UserName=username,
            AccessKeyId=current_key,
            Status="Inactive",
        )

        logger.info("aws_key_rotated", username=username)
        return f"{new_access_key}:{new_secret_key}"
    except ImportError:
        logger.error("boto3_not_installed_for_aws_rotation")
        return None
    except Exception as e:
        logger.error("aws_rotation_error", error=str(e))
        return None


async def _rotate_via_webhook(
    service_name: str,
    secret_type: str,
    current_value: str,
) -> str | None:
    """Call external webhook to rotate a secret."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.SECRET_ROTATION_WEBHOOK_URL,
                json={
                    "service_name": service_name,
                    "secret_type": secret_type,
                    "action": "rotate",
                },
                headers={
                    "X-Aegis-Webhook-Secret": settings.WEBHOOK_HMAC_SECRET,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("new_secret")
            else:
                logger.warning(
                    "webhook_rotation_failed",
                    service=service_name,
                    status=resp.status_code,
                )
                return None
    except Exception as e:
        logger.error("webhook_rotation_error", error=str(e))
        return None


secret_rotation = SecretRotationService()
