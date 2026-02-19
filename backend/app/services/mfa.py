"""
MFA Service — TOTP-based Multi-Factor Authentication.
Uses pyotp for TOTP generation/verification and generates backup codes.
"""
import secrets
from typing import Optional

import pyotp
from passlib.context import CryptContext

from app.logging_config import get_logger

logger = get_logger("mfa")

BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8

# SECURITY: Use bcrypt for backup codes — SHA-256 is too fast for 4-byte entropy codes
_backup_hasher = CryptContext(schemes=["bcrypt"], deprecated="auto")


class MFAService:
    """TOTP multi-factor authentication service."""

    @staticmethod
    def generate_secret() -> str:
        """Generate a new TOTP secret (base32 encoded)."""
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(
        secret: str, email: str, issuer: str = "AEGIS"
    ) -> str:
        """Generate provisioning URI for authenticator apps (QR code)."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)

    @staticmethod
    def verify_code(secret: str, code: str) -> bool:
        """Verify a TOTP code. Allows 1 window tolerance (±30s)."""
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    @staticmethod
    def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
        """Generate one-time backup codes (plain text, shown once to user)."""
        codes = []
        for _ in range(count):
            raw = secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper()
            codes.append(f"{raw[:4]}-{raw[4:]}")
        return codes

    @staticmethod
    def hash_backup_code(code: str) -> str:
        """Hash a backup code with bcrypt for brute-force resistance."""
        normalized = code.strip().upper().replace("-", "")
        return _backup_hasher.hash(normalized)

    @staticmethod
    def verify_backup_code(code: str, hashed_codes: list[str]) -> Optional[int]:
        """
        Verify a backup code against stored bcrypt hashes.
        Returns the index of the matching code (for removal), or None.
        """
        normalized = code.strip().upper().replace("-", "")
        for i, stored_hash in enumerate(hashed_codes):
            try:
                if _backup_hasher.verify(normalized, stored_hash):
                    return i
            except Exception:
                continue
        return None
