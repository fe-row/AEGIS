from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Core ──
    APP_NAME: str = "Aegis Agentic IAM"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://aegis:aegis_secret_2024@localhost:5432/aegis"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # ── Redis ──
    REDIS_URL: str = "redis://:aegis_redis_2024@localhost:6379/0"

    # ── OPA ──
    OPA_URL: str = "http://localhost:8181"

    # ── Auth ──
    JWT_SECRET: str = "CHANGEME-insecure-default-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

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

    @property
    def debug(self) -> bool:
        return self.DEBUG or self.ENVIRONMENT == "development"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()