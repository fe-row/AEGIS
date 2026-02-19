from pydantic_settings import BaseSettings
from functools import lru_cache
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


class Settings(BaseSettings):
    # ── Core ──
    APP_NAME: str = "Aegis Agentic IAM"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://aegis:aegis_secret_2024@localhost:5432/aegis"
    DATABASE_READ_URL: str = ""  # Read replica URL (optional, for HA setups)
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # ── Redis ──
    REDIS_URL: str = "redis://:aegis_redis_2024@localhost:6379/0"
    REDIS_SENTINEL_HOSTS: str = ""  # Comma-separated host:port pairs for Sentinel
    REDIS_SENTINEL_MASTER: str = "mymaster"  # Sentinel master name

    # ── OPA ──
    OPA_URL: str = "http://localhost:8181"

    # ── Auth ──
    JWT_SECRET: str = "CHANGEME-insecure-default-jwt-secret"
    JWT_ALGORITHM: str = "RS256"
    JWT_PRIVATE_KEY: str = ""  # PEM-encoded RSA private key
    JWT_PUBLIC_KEY: str = ""   # PEM-encoded RSA public key
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    @property
    def jwt_signing_key(self) -> str:
        """Key used to SIGN tokens (private key for RS256, secret for HS256)."""
        if self.JWT_ALGORITHM.startswith("RS") and self.JWT_PRIVATE_KEY:
            return self.JWT_PRIVATE_KEY
        return self.JWT_SECRET

    @property
    def jwt_verification_key(self) -> str:
        """Key used to VERIFY tokens (public key for RS256, secret for HS256)."""
        if self.JWT_ALGORITHM.startswith("RS") and self.JWT_PUBLIC_KEY:
            return self.JWT_PUBLIC_KEY
        return self.JWT_SECRET

    # ── Encryption ──
    ENCRYPTION_KEY: str = ""

    # ── CORS ──
    CORS_ORIGINS: str = "http://localhost:3000,https://localhost"

    # ── Domain ──
    DOMAIN: str = "localhost"

    # ── Webhooks ──
    SLACK_WEBHOOK_URL: str = ""
    TEAMS_WEBHOOK_URL: str = ""
    HITL_WEBHOOK_URL: str = ""

    # ── Backups ──
    BACKUP_RETENTION_DAYS: int = 7

    # ── Circuit Breaker ──
    CIRCUIT_BREAKER_THRESHOLD_PCT: float = 300.0
    CIRCUIT_BREAKER_WINDOW_SECONDS: int = 300

    # ── Rate Limiting ──
    GLOBAL_RATE_LIMIT_PER_MINUTE: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # ── JIT Tokens ──
    JIT_TOKEN_TTL_SECONDS: int = 120

    # ── Auth Refresh ──
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Scheduler ──
    AUDIT_FLUSH_INTERVAL_SECONDS: int = 10

    # ── Redis Pool ──
    REDIS_MAX_CONNECTIONS: int = 20

    # ── Trust ──
    INITIAL_TRUST_SCORE: float = 50.0
    MAX_TRUST_SCORE: float = 100.0
    MIN_TRUST_SCORE: float = 0.0

    # ── SSO (OIDC) ──
    SSO_ENABLED: bool = False
    SSO_PROVIDER: str = ""  # "okta", "azure_ad", "google"
    SSO_CLIENT_ID: str = ""
    SSO_CLIENT_SECRET: str = ""
    SSO_DISCOVERY_URL: str = ""  # e.g. https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration
    SSO_REDIRECT_URI: str = ""  # e.g. https://your-domain.com/api/v1/auth/sso/callback

    # ── OpenTelemetry ──
    OTEL_ENABLED: bool = False
    OTEL_EXPORTER_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "aegis-backend"

    # ── Alerting ──
    ALERT_PROVIDER: str = ""  # "pagerduty", "opsgenie", "pagerduty,opsgenie"
    PAGERDUTY_ROUTING_KEY: str = ""
    OPSGENIE_API_KEY: str = ""

    # ── Forensic Export (Immutable Audit Storage) ──
    FORENSIC_STORAGE_BACKEND: str = "local"  # "s3", "gcs", "local", "dry-run"
    FORENSIC_S3_BUCKET: str = ""
    FORENSIC_S3_PREFIX: str = "aegis-audit/"
    FORENSIC_S3_ENDPOINT: str = ""  # Custom S3 endpoint (MinIO, etc.)
    FORENSIC_S3_ACCESS_KEY: str = ""
    FORENSIC_S3_SECRET_KEY: str = ""
    FORENSIC_S3_REGION: str = "us-east-1"
    FORENSIC_RETENTION_DAYS: int = 2555  # ~7 years (SOC2/GDPR)
    FORENSIC_TSA_URL: str = ""  # RFC 3161 TSA server URL (e.g. http://timestamp.digicert.com)
    FORENSIC_LOCAL_PATH: str = "/tmp/aegis-forensic-exports"
    FORENSIC_AUTO_EXPORT_INTERVAL_HOURS: int = 24

    # ── Webhook Security ──
    WEBHOOK_HMAC_SECRET: str = ""  # HMAC-SHA256 key for signing outgoing webhooks
    SECRET_ROTATION_WEBHOOK_URL: str = ""  # External webhook for custom rotation strategies

    # ── Secret Rotation ──
    SECRET_ROTATION_CHECK_INTERVAL_HOURS: int = 1  # How often to check for overdue rotations

    # ── Secrets Management ──
    SECRETS_PROVIDER: str = "env"  # "env", "vault", "aws"
    VAULT_ADDR: str = "http://127.0.0.1:8200"
    VAULT_TOKEN: str = ""
    VAULT_SECRET_PATH: str = "secret"
    AWS_SECRET_NAME: str = "aegis/production"

    @property
    def debug(self) -> bool:
        return self.DEBUG or self.ENVIRONMENT == "development"

    class Config:
        env_file = ".env"


_INSECURE_JWT_DEFAULTS = {
    "change-me-in-production-2024",
    "CHANGEME-insecure-default-jwt-secret",
}


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # SECURITY: Refuse to start in production with a default JWT secret
    if s.ENVIRONMENT == "production" and s.JWT_SECRET in _INSECURE_JWT_DEFAULTS:
        raise RuntimeError(
            "FATAL: JWT_SECRET is set to an insecure default. "
            "Set a strong, unique JWT_SECRET environment variable before running in production."
        )
    # Auto-generate RSA keys for development if RS256 is configured but no keys provided
    if s.JWT_ALGORITHM.startswith("RS") and not s.JWT_PRIVATE_KEY:
        import warnings
        warnings.warn(
            "JWT_PRIVATE_KEY not set — generating ephemeral RSA keys. "
            "Set JWT_PRIVATE_KEY and JWT_PUBLIC_KEY in .env for production.",
            stacklevel=2,
        )
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        s = s.model_copy(update={
            "JWT_PRIVATE_KEY": private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode(),
            "JWT_PUBLIC_KEY": private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode(),
        })
    return s