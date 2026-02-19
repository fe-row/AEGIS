"""
Tests for Forensic Export Service — immutability, chain verification, and export logic.

Validates:
  1. Deep chain verification detects tampered hashes
  2. Deep chain verification detects broken chain links
  3. Batch serialization is deterministic (canonical JSON)
  4. Export marks rows as exported
  5. Immutability trigger tests (conceptual — actual DB triggers tested via migration)
  6. Forensic report generation
"""
import pytest
import json
import uuid
import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.forensic_export import (
    ForensicExportService, _serialize_batch, _verify_batch_chain, GENESIS_HASH,
)
from app.services.audit_service import AuditService
from app.utils.crypto import hash_chain
from app.models.entities import AuditLog, ActionType


# ═══════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════

def _make_audit_log(
    id: int,
    agent_id: uuid.UUID | None = None,
    sponsor_id: uuid.UUID | None = None,
    previous_hash: str = GENESIS_HASH,
    action_type: str = "api_call",
    service_name: str = "openai",
    permission_granted: bool = True,
    cost_usd: float = 0.01,
    timestamp: datetime | None = None,
) -> MagicMock:
    """Create a mock AuditLog with consistent hashing."""
    agent_id = agent_id or uuid.uuid4()
    sponsor_id = sponsor_id or uuid.uuid4()
    ts = timestamp or datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    log_data = json.dumps({
        "agent_id": str(agent_id),
        "sponsor_id": str(sponsor_id),
        "action_type": action_type,
        "service_name": service_name,
        "permission_granted": permission_granted,
        "cost_usd": cost_usd,
        "timestamp": ts.isoformat(),
    }, sort_keys=True)

    log_hash = hash_chain(log_data, previous_hash)

    log = MagicMock(spec=AuditLog)
    log.id = id
    log.log_hash = log_hash
    log.previous_hash = previous_hash
    log.agent_id = agent_id
    log.sponsor_id = sponsor_id
    log.action_type = action_type
    log.service_name = service_name
    log.permission_granted = permission_granted
    log.cost_usd = cost_usd
    log.timestamp = ts
    log.prompt_snippet = None
    log.model_used = None
    log.policy_evaluation = None
    log.response_code = 200
    log.ip_address = "127.0.0.1"
    log.duration_ms = 50
    log.audit_metadata = {}
    log.exported_at = None
    return log


def _build_chain(count: int = 5) -> list[MagicMock]:
    """Build a valid chain of audit log mocks."""
    agent_id = uuid.uuid4()
    sponsor_id = uuid.uuid4()
    chain = []
    prev_hash = GENESIS_HASH

    for i in range(count):
        ts = datetime(2026, 1, 15, 10, i, 0, tzinfo=timezone.utc)
        log = _make_audit_log(
            id=i + 1,
            agent_id=agent_id,
            sponsor_id=sponsor_id,
            previous_hash=prev_hash,
            timestamp=ts,
        )
        prev_hash = log.log_hash
        chain.append(log)
    return chain


# ═══════════════════════════════════════════════════════
#  Chain Verification
# ═══════════════════════════════════════════════════════

class TestBatchChainVerification:
    def test_valid_chain_passes(self):
        """A properly linked chain should pass verification."""
        chain = _build_chain(5)
        result = _verify_batch_chain(chain)
        assert result["valid"] is True
        assert result["checked"] == 5
        assert result["broken_at"] == []

    def test_broken_link_detected(self):
        """Inserting a bad previous_hash breaks the chain."""
        chain = _build_chain(5)
        # Tamper: break link at index 3
        chain[3].previous_hash = "0000_tampered_hash_0000"
        result = _verify_batch_chain(chain)
        assert result["valid"] is False
        assert chain[3].id in result["broken_at"]

    def test_empty_chain(self):
        """Empty chain should be valid."""
        result = _verify_batch_chain([])
        assert result["valid"] is True
        assert result["checked"] == 0

    def test_single_entry_chain(self):
        """Single entry chain should pass (no links to verify)."""
        chain = _build_chain(1)
        result = _verify_batch_chain(chain)
        assert result["valid"] is True
        assert result["checked"] == 1


# ═══════════════════════════════════════════════════════
#  Deep Verification (Recomputes Hashes)
# ═══════════════════════════════════════════════════════

class TestDeepVerification:
    @pytest.mark.asyncio
    async def test_valid_chain_deep_verify(self):
        """Deep verify should pass for a valid chain."""
        chain = _build_chain(5)
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = chain
        db.execute = AsyncMock(return_value=result_mock)

        result = await ForensicExportService.deep_verify_chain(db, limit=100)
        assert result["valid"] is True
        assert result["checked"] == 5
        assert result["tampered"] == []
        assert result["chain_breaks"] == []

    @pytest.mark.asyncio
    async def test_tampered_data_detected(self):
        """Changing data after hash computation should be detected."""
        chain = _build_chain(3)
        # Tamper: modify cost after hashing
        chain[1].cost_usd = 999.99  # was 0.01

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = chain
        db.execute = AsyncMock(return_value=result_mock)

        result = await ForensicExportService.deep_verify_chain(db, limit=100)
        assert result["valid"] is False
        assert len(result["tampered"]) >= 1
        tampered_ids = [t["id"] for t in result["tampered"]]
        assert chain[1].id in tampered_ids

    @pytest.mark.asyncio
    async def test_first_entry_wrong_genesis(self):
        """First entry with wrong genesis hash should be flagged."""
        chain = _build_chain(3)
        chain[0].previous_hash = "bad_genesis_hash"

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = chain
        db.execute = AsyncMock(return_value=result_mock)

        result = await ForensicExportService.deep_verify_chain(db, limit=100, offset=0)
        assert result["valid"] is False
        assert len(result["chain_breaks"]) >= 1
        assert result["chain_breaks"][0]["issue"] == "first_entry_not_genesis"

    @pytest.mark.asyncio
    async def test_empty_table_deep_verify(self):
        """Empty table should return valid."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await ForensicExportService.deep_verify_chain(db, limit=100)
        assert result["valid"] is True
        assert result["checked"] == 0


# ═══════════════════════════════════════════════════════
#  Canonical Serialization
# ═══════════════════════════════════════════════════════

class TestCanonicalSerialization:
    def test_serialization_is_deterministic(self):
        """Same data should always produce the same serialization."""
        chain = _build_chain(3)
        s1 = _serialize_batch(chain)
        s2 = _serialize_batch(chain)
        assert s1 == s2

    def test_serialization_produces_valid_json(self):
        """Output must be valid JSON."""
        chain = _build_chain(3)
        serialized = _serialize_batch(chain)
        parsed = json.loads(serialized)
        assert isinstance(parsed, list)
        assert len(parsed) == 3

    def test_serialization_hash_is_stable(self):
        """Hash of serialized batch should be reproducible."""
        chain = _build_chain(5)
        s1 = _serialize_batch(chain)
        s2 = _serialize_batch(chain)
        h1 = hashlib.sha3_256(s1.encode()).hexdigest()
        h2 = hashlib.sha3_256(s2.encode()).hexdigest()
        assert h1 == h2


# ═══════════════════════════════════════════════════════
#  Export Flow
# ═══════════════════════════════════════════════════════

class TestExportBatch:
    @pytest.mark.asyncio
    async def test_empty_batch_returns_zero(self):
        """No un-exported rows → record_count=0."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await ForensicExportService.export_batch(db, batch_size=100)
        assert result.success is True
        assert result.record_count == 0

    @pytest.mark.asyncio
    async def test_export_with_local_backend(self):
        """Export to local storage should succeed."""
        chain = _build_chain(3)

        db = AsyncMock()

        # First call: select logs
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = chain
        # Subsequent calls: update + insert
        db.execute = AsyncMock(return_value=select_result)
        db.commit = AsyncMock()

        with patch("app.services.forensic_export.settings") as mock_settings:
            mock_settings.FORENSIC_STORAGE_BACKEND = "local"
            mock_settings.FORENSIC_TSA_URL = ""
            mock_settings.FORENSIC_LOCAL_PATH = "/tmp/aegis-test-exports"

            with patch("app.services.forensic_export._upload_local", new_callable=AsyncMock) as mock_upload:
                mock_upload.return_value = "file:///tmp/aegis-test-exports/test.json"

                result = await ForensicExportService.export_batch(
                    db, batch_size=100, exported_by="test@aegis.io",
                )

        assert result.success is True
        assert result.record_count == 3
        assert result.batch_hash != ""
        assert result.from_id == chain[0].id
        assert result.to_id == chain[-1].id

    @pytest.mark.asyncio
    async def test_export_fails_on_broken_chain(self):
        """Export should refuse if chain integrity is broken."""
        chain = _build_chain(3)
        chain[2].previous_hash = "broken_link"

        db = AsyncMock()
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = chain
        db.execute = AsyncMock(return_value=select_result)

        with patch("app.services.forensic_export.settings") as mock_settings:
            mock_settings.FORENSIC_STORAGE_BACKEND = "local"
            mock_settings.FORENSIC_TSA_URL = ""

            result = await ForensicExportService.export_batch(
                db, batch_size=100, exported_by="test@aegis.io",
            )

        assert result.success is False
        assert "integrity" in (result.error or "").lower()


# ═══════════════════════════════════════════════════════
#  Forensic Report
# ═══════════════════════════════════════════════════════

class TestForensicReport:
    @pytest.mark.asyncio
    async def test_report_generation(self):
        """Report should contain stats and integrity info."""
        chain = _build_chain(5)
        # Mark some as denied
        chain[1].permission_granted = False
        chain[3].permission_granted = False

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = chain
        db.execute = AsyncMock(return_value=result_mock)

        report = await ForensicExportService.generate_forensic_report(db, 1, 5)
        assert report["record_count"] == 5
        assert report["batch_hash"] != ""
        assert report["statistics"]["denied_actions"] == 2
        assert report["statistics"]["granted_actions"] == 3
        assert report["statistics"]["unique_agents"] == 1

    @pytest.mark.asyncio
    async def test_empty_report(self):
        """No logs in range → error response."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        report = await ForensicExportService.generate_forensic_report(db, 999, 1000)
        assert "error" in report


# ═══════════════════════════════════════════════════════
#  Hash Chain Crypto
# ═══════════════════════════════════════════════════════

class TestHashChainCrypto:
    def test_hash_chain_deterministic(self):
        """Same input → same hash, always."""
        h1 = hash_chain("test_data", "previous_hash")
        h2 = hash_chain("test_data", "previous_hash")
        assert h1 == h2

    def test_hash_chain_different_data(self):
        """Different data → different hash."""
        h1 = hash_chain("data_a", "prev")
        h2 = hash_chain("data_b", "prev")
        assert h1 != h2

    def test_hash_chain_different_previous(self):
        """Different previous hash → different output."""
        h1 = hash_chain("data", "prev_a")
        h2 = hash_chain("data", "prev_b")
        assert h1 != h2

    def test_hash_chain_uses_sha3_256(self):
        """Verify SHA3-256 output format."""
        h = hash_chain("test", "0" * 64)
        assert len(h) == 64  # SHA3-256 hex digest is 64 chars
        assert all(c in "0123456789abcdef" for c in h)

    def test_genesis_hash_format(self):
        """Genesis hash should be 64 zeros."""
        assert GENESIS_HASH == "0" * 64
        assert len(GENESIS_HASH) == 64


# ═══════════════════════════════════════════════════════
#  Immutability Trigger (Conceptual)
#  Actual trigger is tested at DB level via migration
# ═══════════════════════════════════════════════════════

class TestImmutabilityInvariants:
    def test_audit_log_has_tsa_column(self):
        """AuditLog model should have tsa_token and exported_at columns."""
        columns = {c.name for c in AuditLog.__table__.columns}
        assert "tsa_token" in columns
        assert "exported_at" in columns

    def test_audit_log_hash_columns_not_nullable(self):
        """log_hash and previous_hash must be NOT NULL."""
        log_hash_col = AuditLog.__table__.c.log_hash
        previous_hash_col = AuditLog.__table__.c.previous_hash
        assert log_hash_col.nullable is False
        assert previous_hash_col.nullable is False

    def test_audit_log_hash_is_unique(self):
        """log_hash must have a unique constraint."""
        log_hash_col = AuditLog.__table__.c.log_hash
        assert log_hash_col.unique is True
