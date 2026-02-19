"""Float to Numeric for all USD monetary columns.

Revision ID: 001_float_to_numeric
Revises:
Create Date: 2026-02-19

Prevents floating-point precision errors in financial calculations
by switching all USD columns from Float to Numeric(12, 6).
"""
from alembic import op
import sqlalchemy as sa

revision = "001_float_to_numeric"
down_revision = "000_initial_schema"
branch_labels = None
depends_on = None

# (table, column) pairs that hold monetary values
USD_COLUMNS = [
    ("micro_wallets", "balance_usd"),
    ("micro_wallets", "daily_limit_usd"),
    ("micro_wallets", "monthly_limit_usd"),
    ("micro_wallets", "spent_today_usd"),
    ("micro_wallets", "spent_this_month_usd"),
    ("wallet_transactions", "amount_usd"),
    ("audit_logs", "cost_usd"),
    ("hitl_requests", "estimated_cost_usd"),
    ("behavior_profiles", "avg_cost_per_action"),
]


def upgrade() -> None:
    for table, column in USD_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Float(),
            type_=sa.Numeric(precision=12, scale=6),
            existing_nullable=True,
            postgresql_using=f"{column}::numeric(12,6)",
        )


def downgrade() -> None:
    for table, column in USD_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Numeric(precision=12, scale=6),
            type_=sa.Float(),
            existing_nullable=True,
        )
