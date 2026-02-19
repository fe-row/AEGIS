"""
Webhook HMAC Signer — Signs outgoing webhook payloads and verifies incoming ones.

All AEGIS webhooks (HITL, Slack, Teams, rotation) are signed with HMAC-SHA256
so recipients can verify authenticity and prevent spoofed approval attacks.
"""
import hashlib
import hmac
import time
import json
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("webhook_signer")
settings = get_settings()


def sign_payload(payload: dict | str, secret: str | None = None) -> dict:
    """
    Sign a webhook payload with HMAC-SHA256.

    Returns headers to include in the webhook request:
      X-Aegis-Signature: sha256=<hex_digest>
      X-Aegis-Timestamp: <unix_timestamp>
    """
    signing_secret = secret or settings.WEBHOOK_HMAC_SECRET
    if not signing_secret:
        logger.warning("webhook_sign_no_secret")
        return {}

    timestamp = str(int(time.time()))

    if isinstance(payload, dict):
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    else:
        body = payload

    # Sign: timestamp + "." + body (prevents replay attacks)
    message = f"{timestamp}.{body}"
    signature = hmac.new(
        signing_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-Aegis-Signature": f"sha256={signature}",
        "X-Aegis-Timestamp": timestamp,
    }


def verify_signature(
    payload: str,
    signature_header: str,
    timestamp_header: str,
    secret: str | None = None,
    max_age_seconds: int = 300,
) -> bool:
    """
    Verify an incoming webhook signature.

    Args:
        payload: Raw request body as string
        signature_header: Value of X-Aegis-Signature header
        timestamp_header: Value of X-Aegis-Timestamp header
        secret: HMAC secret (defaults to WEBHOOK_HMAC_SECRET)
        max_age_seconds: Maximum age of the timestamp (prevents replay)

    Returns:
        True if signature is valid and timestamp is fresh
    """
    signing_secret = secret or settings.WEBHOOK_HMAC_SECRET
    if not signing_secret:
        logger.warning("webhook_verify_no_secret")
        return False

    # Check timestamp freshness (anti-replay)
    try:
        ts = int(timestamp_header)
        age = abs(time.time() - ts)
        if age > max_age_seconds:
            logger.warning("webhook_timestamp_expired", age_seconds=age)
            return False
    except (ValueError, TypeError):
        logger.warning("webhook_invalid_timestamp")
        return False

    # Verify HMAC
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header[7:]  # strip "sha256="
    message = f"{timestamp_header}.{payload}"
    computed = hmac.new(
        signing_secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)
