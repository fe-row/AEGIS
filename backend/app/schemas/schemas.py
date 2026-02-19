from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID
import re
from app.models.entities import AgentStatus, ActionType, HITLStatus, UserRole


# ── Helpers ──

def _validate_password_complexity(v: str) -> str:
    """Shared password complexity rules for registration and password change."""
    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", v):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", v):
        raise ValueError("Password must contain at least one special character")
    return v


# ── Auth ──

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str
    organization: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    organization: Optional[str]
    role: UserRole
    is_active: bool
    mfa_enabled: bool = False
    sso_provider: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── API Keys ──

class APIKeyCreate(BaseModel):
    name: str = Field(max_length=100)
    scopes: List[str] = []


class APIKeyCreated(BaseModel):
    id: UUID
    key_prefix: str
    name: str
    scopes: List[str]
    is_active: bool
    created_at: datetime
    raw_key: str

    model_config = ConfigDict(from_attributes=True)


class APIKeyOut(BaseModel):
    id: UUID
    key_prefix: str
    name: str
    scopes: List[str]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_complexity(v)


# ── Agents ──

class AgentCreate(BaseModel):
    name: str = Field(max_length=200)
    description: Optional[str] = ""
    agent_type: str = Field(max_length=100)
    metadata_: Optional[dict] = {}


class AgentOut(BaseModel):
    id: UUID
    name: str
    description: str
    agent_type: str
    status: AgentStatus
    trust_score: float
    identity_fingerprint: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentDetail(AgentOut):
    wallet_balance: Optional[float] = None
    active_permissions: int = 0
    total_actions_24h: int = 0


# ── Permissions ──

class PermissionCreate(BaseModel):
    service_name: str
    allowed_actions: List[str] = ["read"]
    max_requests_per_hour: int = 100
    time_window_start: str = "00:00"
    time_window_end: str = "23:59"
    max_records_per_request: int = 100
    requires_hitl: bool = False
    custom_policy: Optional[str] = None


class PermissionOut(BaseModel):
    id: UUID
    service_name: str
    allowed_actions: List[str]
    max_requests_per_hour: int
    time_window_start: str
    time_window_end: str
    requires_hitl: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ── Secrets ──

class SecretStore(BaseModel):
    service_name: str
    secret_value: str
    secret_type: str = "api_key"
    rotation_interval_hours: int = 0


# ── Wallets ──

class WalletConfig(BaseModel):
    balance_usd: float = 0.0
    daily_limit_usd: float = 10.0
    monthly_limit_usd: float = 200.0


class WalletOut(BaseModel):
    id: UUID
    agent_id: UUID
    balance_usd: float
    daily_limit_usd: float
    monthly_limit_usd: float
    spent_today_usd: float
    spent_this_month_usd: float
    is_frozen: bool

    model_config = ConfigDict(from_attributes=True)


class WalletTopUp(BaseModel):
    amount_usd: float = Field(gt=0)


# ── Proxy Execution ──

class ProxyRequest(BaseModel):
    agent_id: UUID
    service_name: str
    action: str  # "read", "write", "delete"
    target_url: str
    method: str = "GET"
    headers: Optional[dict] = {}
    body: Optional[Any] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    estimated_cost_usd: float = 0.0


class ProxyResponse(BaseModel):
    request_id: UUID
    status: str  # "executed", "blocked", "hitl_pending"
    response_code: Optional[int] = None
    response_body: Optional[Any] = None
    cost_charged_usd: float = 0.0
    policy_result: Optional[dict] = None
    message: str = ""
    duration_ms: Optional[int] = None


# ── HITL ──

class HITLDecision(BaseModel):
    approved: bool
    note: Optional[str] = ""


class HITLOut(BaseModel):
    id: UUID
    agent_id: UUID
    action_description: str
    estimated_cost_usd: float
    status: HITLStatus
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Audit ──

class AuditLogOut(BaseModel):
    id: int
    agent_id: UUID
    action_type: ActionType
    service_name: Optional[str]
    permission_granted: bool
    cost_usd: float
    response_code: Optional[int]
    duration_ms: Optional[int]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Dashboard ──

class DashboardStats(BaseModel):
    total_agents: int
    active_agents: int
    suspended_agents: int
    total_requests_24h: int
    total_blocked_24h: int
    total_spend_24h: float
    total_spend_month: float
    avg_trust_score: float
    pending_hitl: int
    circuit_breaker_triggers_24h: int
    hourly_spend: List[dict] = []
    top_services: List[dict] = []


class TrustScoreUpdate(BaseModel):
    agent_id: UUID
    new_score: float
    reason: str


# ── RBAC ──

class RoleCreate(BaseModel):
    name: str = Field(max_length=100)
    description: str = ""
    permissions: List[str] = []


class RoleOut(BaseModel):
    id: UUID
    name: str
    description: str
    permissions: List[str]
    is_system: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoleAssign(BaseModel):
    user_id: UUID
    role_id: UUID


class UserRoleUpdate(BaseModel):
    role: UserRole


# ── MFA ──

class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    backup_codes: List[str]


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MFAChallengeRequest(BaseModel):
    email: str
    mfa_token: str
    code: str


class LoginResponse(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"
    expires_in: int = 0
    mfa_required: bool = False
    mfa_token: str = ""


# ── SSO ──

class SSOAuthorizeResponse(BaseModel):
    authorize_url: str


class SSOCallbackRequest(BaseModel):
    code: str
    state: str