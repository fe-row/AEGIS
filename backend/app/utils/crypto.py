import hashlib
import secrets
from cryptography.fernet import Fernet
from app.config import get_settings
from app.logging_config import get_logger

settings = get_settings()
logger = get_logger("crypto")

_fernet_key = settings.ENCRYPTION_KEY
if not _fernet_key:
    logger.warning(
        "ENCRYPTION_KEY not set — using ephemeral key. "
        "Encrypted data will be UNRECOVERABLE after restart!"
    )
    _fernet_key = Fernet.generate_key().decode()

_fernet = Fernet(_fernet_key.encode() if isinstance(_fernet_key, str) else _fernet_key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except Exception as exc:
        raise ValueError(f"Decryption failed: {exc}") from exc


def generate_identity_fingerprint(agent_name: str, sponsor_id: str) -> str:
    seed = f"{agent_name}:{sponsor_id}:{secrets.token_hex(16)}"
    return hashlib.sha3_256(seed.encode()).hexdigest()


def generate_ephemeral_token() -> str:
    return secrets.token_urlsafe(48)


def hash_chain(data: str, previous_hash: str) -> str:
    """Produce hash for immutable audit chain."""
    payload = f"{previous_hash}:{data}"
    return hashlib.sha3_256(payload.encode()).hexdigest()


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key. Returns (raw_key, key_hash)."""
    raw_key = f"aegis_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(raw_key)
    return raw_key, key_hash