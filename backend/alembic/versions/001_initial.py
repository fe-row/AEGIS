"""Initial schema — all 10 tables

Revision ID: 001_initial
Revises: None
Create Date: 2026-02-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Users ──
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("organization", sa.String(200)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("is_superadmin", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── User API Keys ──
    op.create_table(
        "user_api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(20), nullable=False, server_default=""),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scopes", JSONB, server_default="[]"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Agents ──
    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sponsor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("agent_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("trust_score", sa.Float, server_default="50.0"),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("pq_public_key", sa.Text, nullable=True),
        sa.Column("identity_fingerprint", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_agents_sponsor", "agents", ["sponsor_id"])
    op.create_index("idx_agents_status", "agents", ["status"])
    op.create_index("idx_agents_type", "agents", ["agent_type"])

    # ── Secret Vault ──
    op.create_table(
        "secret_vault",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sponsor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("service_name", sa.String(200), nullable=False),
        sa.Column("encrypted_secret", sa.Text, nullable=False),
        sa.Column("secret_type", sa.String(50), server_default="api_key"),
        sa.Column("rotation_interval_hours", sa.Integer, server_default="0"),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_vault_sponsor_service", "secret_vault", ["sponsor_id", "service_name"], unique=True)

    # ── Agent Permissions ──
    op.create_table(
        "agent_permissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("service_name", sa.String(200), nullable=False),
        sa.Column("allowed_actions", JSONB, server_default="[]"),
        sa.Column("max_requests_per_hour", sa.Integer, server_default="100"),
        sa.Column("time_window_start", sa.String(5), server_default="00:00"),
        sa.Column("time_window_end", sa.String(5), server_default="23:59"),
        sa.Column("max_records_per_request", sa.Integer, server_default="100"),
        sa.Column("requires_hitl", sa.Boolean, server_default=sa.text("false")),
        sa.Column("custom_policy", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_perms_agent_service", "agent_permissions", ["agent_id", "service_name"])

    # ── Micro Wallets ──
    op.create_table(
        "micro_wallets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False, unique=True),
        sa.Column("balance_usd", sa.Float, server_default="0.0"),
        sa.Column("daily_limit_usd", sa.Float, server_default="10.0"),
        sa.Column("monthly_limit_usd", sa.Float, server_default="200.0"),
        sa.Column("spent_today_usd", sa.Float, server_default="0.0"),
        sa.Column("spent_this_month_usd", sa.Float, server_default="0.0"),
        sa.Column("last_reset_daily", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_reset_monthly", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_frozen", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Wallet Transactions ──
    op.create_table(
        "wallet_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wallet_id", UUID(as_uuid=True), sa.ForeignKey("micro_wallets.id"), nullable=False),
        sa.Column("amount_usd", sa.Float, nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("service_name", sa.String(200)),
        sa.Column("action_type", sa.String(20)),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_tx_wallet_time", "wallet_transactions", ["wallet_id", "timestamp"])

    # ── Audit Logs (immutable chain) ──
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("log_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("previous_hash", sa.String(128), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("sponsor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action_type", sa.String(20), nullable=False),
        sa.Column("service_name", sa.String(200)),
        sa.Column("prompt_snippet", sa.Text),
        sa.Column("model_used", sa.String(100)),
        sa.Column("permission_granted", sa.Boolean),
        sa.Column("policy_evaluation", JSONB),
        sa.Column("cost_usd", sa.Float, server_default="0.0"),
        sa.Column("response_code", sa.Integer),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index("idx_audit_agent_time", "audit_logs", ["agent_id", "timestamp"])
    op.create_index("idx_audit_service", "audit_logs", ["service_name"])
    op.create_index("idx_audit_sponsor", "audit_logs", ["sponsor_id"])

    # ── HITL Requests ──
    op.create_table(
        "hitl_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("sponsor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action_description", sa.Text, nullable=False),
        sa.Column("action_payload", JSONB),
        sa.Column("estimated_cost_usd", sa.Float, server_default="0.0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("decided_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decision_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_hitl_status", "hitl_requests", ["status"])
    op.create_index("idx_hitl_agent", "hitl_requests", ["agent_id"])
    op.create_index("idx_hitl_sponsor", "hitl_requests", ["sponsor_id"])

    # ── Behavior Profiles ──
    op.create_table(
        "behavior_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False, unique=True),
        sa.Column("typical_services", JSONB, server_default="[]"),
        sa.Column("typical_hours", JSONB, server_default="{}"),
        sa.Column("avg_requests_per_hour", sa.Float, server_default="0.0"),
        sa.Column("avg_cost_per_action", sa.Float, server_default="0.0"),
        sa.Column("feature_vector", JSONB, server_default="[]"),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── State Snapshots ──
    op.create_table(
        "state_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("audit_log_id", sa.BigInteger, sa.ForeignKey("audit_logs.id"), nullable=False),
        sa.Column("snapshot_data", JSONB, nullable=False),
        sa.Column("rollback_instructions", JSONB),
        sa.Column("is_rolled_back", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_snapshot_agent", "state_snapshots", ["agent_id"])


def downgrade() -> None:
    op.drop_table("state_snapshots")
    op.drop_table("behavior_profiles")
    op.drop_table("hitl_requests")
    op.drop_table("audit_logs")
    op.drop_table("wallet_transactions")
    op.drop_table("micro_wallets")
    op.drop_table("agent_permissions")
    op.drop_table("secret_vault")
    op.drop_table("agents")
    op.drop_table("user_api_keys")
    op.drop_table("users")
