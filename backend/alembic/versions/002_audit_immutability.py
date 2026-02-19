"""Audit log immutability — DB triggers + forensic columns

Adds PostgreSQL triggers that prevent DELETE and UPDATE on audit_logs,
making the table append-only at the database level. Also adds columns
for RFC 3161 TSA timestamping and immutable export tracking.

Revision ID: 002_audit_immutability
Revises: 001_initial
Create Date: 2026-02-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_audit_immutability"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Prevent DELETE on audit_logs ──
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'IMMUTABILITY VIOLATION: DELETE on audit_logs is prohibited. '
                'Row id=%, hash=%. Contact security team for forensic procedures.',
                OLD.id, OLD.log_hash
            USING ERRCODE = 'restrict_violation';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_delete();
    """)

    # ── 2. Prevent UPDATE on critical audit columns ──
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_update()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.log_hash IS DISTINCT FROM NEW.log_hash
               OR OLD.previous_hash IS DISTINCT FROM NEW.previous_hash
               OR OLD.agent_id IS DISTINCT FROM NEW.agent_id
               OR OLD.sponsor_id IS DISTINCT FROM NEW.sponsor_id
               OR OLD.action_type IS DISTINCT FROM NEW.action_type
               OR OLD.service_name IS DISTINCT FROM NEW.service_name
               OR OLD.permission_granted IS DISTINCT FROM NEW.permission_granted
               OR OLD.cost_usd IS DISTINCT FROM NEW.cost_usd
               OR OLD.timestamp IS DISTINCT FROM NEW.timestamp
               OR OLD.prompt_snippet IS DISTINCT FROM NEW.prompt_snippet
               OR OLD.policy_evaluation IS DISTINCT FROM NEW.policy_evaluation
               OR OLD.response_code IS DISTINCT FROM NEW.response_code
               OR OLD.ip_address IS DISTINCT FROM NEW.ip_address
               OR OLD.duration_ms IS DISTINCT FROM NEW.duration_ms
            THEN
                RAISE EXCEPTION
                    'IMMUTABILITY VIOLATION: UPDATE on audit_logs core columns is prohibited. '
                    'Row id=%, hash=%. Only tsa_token and exported_at may be updated.',
                    OLD.id, OLD.log_hash
                USING ERRCODE = 'restrict_violation';
                RETURN NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_update();
    """)

    # ── 3. Add forensic columns (TSA + export tracking) ──
    op.add_column("audit_logs", sa.Column(
        "tsa_token", sa.LargeBinary, nullable=True,
        comment="RFC 3161 Timestamp Authority response token",
    ))
    op.add_column("audit_logs", sa.Column(
        "exported_at", sa.DateTime(timezone=True), nullable=True,
        comment="When this entry was exported to immutable storage",
    ))

    # ── 4. Create immutable_exports tracking table ──
    op.create_table(
        "immutable_exports",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("export_hash", sa.String(128), nullable=False, unique=True,
                  comment="SHA3-256 hash of the exported batch"),
        sa.Column("from_id", sa.BigInteger, nullable=False,
                  comment="First audit_log.id in batch"),
        sa.Column("to_id", sa.BigInteger, nullable=False,
                  comment="Last audit_log.id in batch"),
        sa.Column("record_count", sa.Integer, nullable=False),
        sa.Column("storage_backend", sa.String(50), nullable=False,
                  comment="s3, gcs, azure_blob, local"),
        sa.Column("storage_path", sa.String(1000), nullable=False,
                  comment="Full path/key in the storage backend"),
        sa.Column("tsa_token", sa.LargeBinary, nullable=True,
                  comment="RFC 3161 TSA token for the batch hash"),
        sa.Column("exported_by", sa.String(200), nullable=False,
                  comment="User or system that triggered the export"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── 5. Prevent tampering with export records ──
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_export_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                    'IMMUTABILITY VIOLATION: DELETE on immutable_exports is prohibited.'
                USING ERRCODE = 'restrict_violation';
                RETURN NULL;
            END IF;
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION
                    'IMMUTABILITY VIOLATION: UPDATE on immutable_exports is prohibited.'
                USING ERRCODE = 'restrict_violation';
                RETURN NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_exports_immutable
        BEFORE UPDATE OR DELETE ON immutable_exports
        FOR EACH ROW
        EXECUTE FUNCTION prevent_export_mutation();
    """)


def downgrade() -> None:
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS trg_exports_immutable ON immutable_exports;")
    op.execute("DROP FUNCTION IF EXISTS prevent_export_mutation();")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_update();")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_no_delete ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_delete();")

    # Drop table and columns
    op.drop_table("immutable_exports")
    op.drop_column("audit_logs", "exported_at")
    op.drop_column("audit_logs", "tsa_token")
