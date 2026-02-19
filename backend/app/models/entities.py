import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Integer, Enum as SAEnum, Index, BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.models.database import Base


def utcnow():
    return datetime.now(timezone.utc)


# ── Enums ──

class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    SECURITY_MANAGER = "security_manager"
    FINANCE_AUDITOR = "finance_auditor"
    AGENT_DEVELOPER = "agent_developer"
    VIEWER = "viewer"


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    PANIC = "panic"


class ActionType(str, enum.Enum):
    API_CALL = "api_call"
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    DATA_DELETE = "data_delete"
    TRANSACTION = "transaction"
    LLM_INFERENCE = "llm_inference"


class HITLStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


# ── Users (Human Sponsors) ──

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # Nullable for SSO-only users
    full_name = Column(String(200), nullable=False)
    organization = Column(String(200))
    role = Column(SAEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)

    # ── MFA ──
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(Text, nullable=True)  # Encrypted TOTP secret
    mfa_backup_codes = Column(JSONB, default=list)  # Hashed backup codes

    # ── SSO ──
    sso_provider = Column(String(50), nullable=True)  # "okta", "azure_ad", "google"
    sso_subject_id = Column(String(255), nullable=True)  # IdP subject identifier

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    agents = relationship("Agent", back_populates="sponsor")
    api_keys = relationship("UserAPIKey", back_populates="user")
    role_assignments = relationship("UserRoleAssignment", back_populates="user")


class UserAPIKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    key_prefix = Column(String(20), nullable=False, default="")
    name = Column(String(100), nullable=False)
    scopes = Column(JSONB, default=list)  # ["agents:read", "proxy:execute"]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")


# ── Custom Roles ──

class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, default="")
    permissions = Column(JSONB, default=list)  # ["agents:read", "wallets:write", ...]
    is_system = Column(Boolean, default=False)  # True for built-in roles
    created_at = Column(DateTime(timezone=True), default=utcnow)

    assignments = relationship("UserRoleAssignment", back_populates="role")


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="role_assignments", foreign_keys=[user_id])
    role = relationship("Role", back_populates="assignments")

    __table_args__ = (
        Index("idx_ura_user_role", "user_id", "role_id", unique=True),
    )


# ── Agent (Non-Human Identity) ──

class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sponsor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    agent_type = Column(String(100), nullable=False)  # e.g., "sales", "support", "devops"
    status = Column(SAEnum(AgentStatus), default=AgentStatus.ACTIVE)
    trust_score = Column(Float, default=50.0)
    metadata_ = Column("metadata", JSONB, default=dict)

    # Post-Quantum identity fields
    pq_public_key = Column(Text, nullable=True)
    identity_fingerprint = Column(String(128), nullable=False, unique=True)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    sponsor = relationship("User", back_populates="agents")
    wallet = relationship("MicroWallet", back_populates="agent", uselist=False)
    permissions = relationship("AgentPermission", back_populates="agent")
    audit_logs = relationship("AuditLog", back_populates="agent")
    behavior_profile = relationship("BehaviorProfile", back_populates="agent", uselist=False)

    __table_args__ = (
        Index("idx_agents_sponsor", "sponsor_id"),
        Index("idx_agents_status", "status"),
        Index("idx_agents_type", "agent_type"),
    )


# ── Secrets Vault ──

class SecretVault(Base):
    __tablename__ = "secret_vault"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sponsor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    service_name = Column(String(200), nullable=False)  # e.g., "openai", "stripe", "salesforce"
    encrypted_secret = Column(Text, nullable=False)
    secret_type = Column(String(50), default="api_key")  # api_key, oauth_token, certificate
    rotation_interval_hours = Column(Integer, default=0)  # 0 = no rotation
    last_rotated_at = Column(DateTime(timezone=True), default=utcnow)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_vault_sponsor_service", "sponsor_id", "service_name", unique=True),
    )


# ── Agent Permissions ──

class AgentPermission(Base):
    __tablename__ = "agent_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    service_name = Column(String(200), nullable=False)
    allowed_actions = Column(JSONB, default=list)  # ["read", "write"]
    max_requests_per_hour = Column(Integer, default=100)
    time_window_start = Column(String(5), default="00:00")  # HH:MM
    time_window_end = Column(String(5), default="23:59")
    max_records_per_request = Column(Integer, default=100)
    requires_hitl = Column(Boolean, default=False)
    custom_policy = Column(Text, nullable=True)  # Rego override
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    agent = relationship("Agent", back_populates="permissions")

    __table_args__ = (
        Index("idx_perms_agent_service", "agent_id", "service_name"),
    )


# ── Micro-Wallets ──

class MicroWallet(Base):
    __tablename__ = "micro_wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, unique=True)
    balance_usd = Column(Float, default=0.0)
    daily_limit_usd = Column(Float, default=10.0)
    monthly_limit_usd = Column(Float, default=200.0)
    spent_today_usd = Column(Float, default=0.0)
    spent_this_month_usd = Column(Float, default=0.0)
    last_reset_daily = Column(DateTime(timezone=True), default=utcnow)
    last_reset_monthly = Column(DateTime(timezone=True), default=utcnow)
    is_frozen = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    agent = relationship("Agent", back_populates="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("micro_wallets.id"), nullable=False)
    amount_usd = Column(Float, nullable=False)
    description = Column(String(500))
    service_name = Column(String(200))
    action_type = Column(SAEnum(ActionType))
    timestamp = Column(DateTime(timezone=True), default=utcnow)

    wallet = relationship("MicroWallet", back_populates="transactions")

    __table_args__ = (
        Index("idx_tx_wallet_time", "wallet_id", "timestamp"),
    )


# ── Immutable Audit Log ──

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    log_hash = Column(String(128), nullable=False, unique=True)
    previous_hash = Column(String(128), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    sponsor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type = Column(SAEnum(ActionType), nullable=False)
    service_name = Column(String(200))
    prompt_snippet = Column(Text)  # First 500 chars of prompt
    model_used = Column(String(100))
    permission_granted = Column(Boolean)
    policy_evaluation = Column(JSONB)  # OPA result
    cost_usd = Column(Float, default=0.0)
    response_code = Column(Integer)
    ip_address = Column(String(45))
    duration_ms = Column(Integer)
    audit_metadata = Column("metadata", JSONB, default=dict)
    timestamp = Column(DateTime(timezone=True), default=utcnow, index=True)

    agent = relationship("Agent", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_agent_time", "agent_id", "timestamp"),
        Index("idx_audit_service", "service_name"),
        Index("idx_audit_sponsor", "sponsor_id"),
    )


# ── HITL Requests ──

class HITLRequest(Base):
    __tablename__ = "hitl_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    sponsor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_description = Column(Text, nullable=False)
    action_payload = Column(JSONB)
    estimated_cost_usd = Column(Float, default=0.0)
    status = Column(SAEnum(HITLStatus), default=HITLStatus.PENDING)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decision_note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_hitl_status", "status"),
        Index("idx_hitl_agent", "agent_id"),
        Index("idx_hitl_sponsor", "sponsor_id"),
        Index("idx_hitl_sponsor_status", "sponsor_id", "status"),
    )


# ── Behavior Profiles (Anomaly Detection) ──

class BehaviorProfile(Base):
    __tablename__ = "behavior_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, unique=True)
    typical_services = Column(JSONB, default=list)  # services normally accessed
    typical_hours = Column(JSONB, default=dict)  # hour -> frequency map
    avg_requests_per_hour = Column(Float, default=0.0)
    avg_cost_per_action = Column(Float, default=0.0)
    feature_vector = Column(JSONB, default=list)  # for ML model
    last_updated = Column(DateTime(timezone=True), default=utcnow)

    agent = relationship("Agent", back_populates="behavior_profile")


# ── State Snapshots (Rollback) ──

class StateSnapshot(Base):
    __tablename__ = "state_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    audit_log_id = Column(BigInteger, ForeignKey("audit_logs.id"), nullable=False)
    snapshot_data = Column(JSONB, nullable=False)
    rollback_instructions = Column(JSONB)
    is_rolled_back = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_snapshot_agent", "agent_id"),
    )