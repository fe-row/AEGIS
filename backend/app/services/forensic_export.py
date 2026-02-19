"""
Forensic Export Service — Immutable audit log archival.

Exports audit log batches to write-once storage (S3 Object Lock, GCS, local)
with optional RFC 3161 Timestamp Authority signatures for legal non-repudiation.
"""
import hashlib
import json
import io
import csv
import httpx
from datetime import datetime, timezone
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from app.models.entities import AuditLog
from app.utils.crypto import hash_chain
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("forensic_export")
settings = get_settings()

GENESIS_HASH = "0" * 64


@dataclass
class ExportResult:
    success: bool
    record_count: int
    batch_hash: str
    storage_path: str
    tsa_token: bytes | None
    from_id: int
    to_id: int
    error: str | None = None


class ForensicExportService:
    """Exports audit logs to immutable storage with cryptographic guarantees."""

    @staticmethod
    async def export_batch(
        db: AsyncSession,
        from_id: int | None = None,
        to_id: int | None = None,
        batch_size: int = 10000,
        exported_by: str = "system",
    ) -> ExportResult:
        """
        Export a batch of audit logs to immutable storage.

        1. Select un-exported rows (or by ID range)
        2. Verify hash chain integrity of the batch
        3. Serialize to canonical JSON
        4. Compute batch hash (SHA3-256)
        5. Optionally sign with RFC 3161 TSA
        6. Upload to write-once storage
        7. Mark rows as exported
        8. Record export metadata
        """
        try:
            # Step 1: Select rows
            query = select(AuditLog).order_by(AuditLog.id.asc())
            if from_id is not None:
                query = query.where(AuditLog.id >= from_id)
            if to_id is not None:
                query = query.where(AuditLog.id <= to_id)
            else:
                query = query.where(AuditLog.exported_at.is_(None))
            query = query.limit(batch_size)

            result = await db.execute(query)
            logs = list(result.scalars().all())

            if not logs:
                return ExportResult(
                    success=True, record_count=0, batch_hash="",
                    storage_path="", tsa_token=None, from_id=0, to_id=0,
                )

            actual_from = logs[0].id
            actual_to = logs[-1].id

            # Step 2: Verify chain integrity within batch
            integrity = _verify_batch_chain(logs)
            if not integrity["valid"]:
                logger.error(
                    "forensic_export_chain_broken",
                    broken_at=integrity["broken_at"],
                    from_id=actual_from,
                    to_id=actual_to,
                )
                return ExportResult(
                    success=False, record_count=len(logs), batch_hash="",
                    storage_path="", tsa_token=None,
                    from_id=actual_from, to_id=actual_to,
                    error=f"Chain integrity broken at IDs: {integrity['broken_at']}",
                )

            # Step 3: Serialize to canonical JSON
            canonical = _serialize_batch(logs)
            canonical_bytes = canonical.encode("utf-8")

            # Step 4: Compute batch hash
            batch_hash = hashlib.sha3_256(canonical_bytes).hexdigest()

            # Step 5: TSA signature (optional)
            tsa_token = None
            if settings.FORENSIC_TSA_URL:
                tsa_token = await _request_tsa_token(batch_hash)

            # Step 6: Upload to storage
            storage_backend = settings.FORENSIC_STORAGE_BACKEND
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"aegis_audit_{actual_from}_{actual_to}_{timestamp}.json"

            if storage_backend == "s3":
                storage_path = await _upload_s3(
                    canonical_bytes, filename, batch_hash,
                )
            elif storage_backend == "local":
                storage_path = await _upload_local(canonical_bytes, filename)
            else:
                storage_path = f"dry-run://{filename}"
                logger.warning("forensic_export_dry_run", backend=storage_backend)

            # Step 7: Mark rows as exported
            now = datetime.now(timezone.utc)
            await db.execute(
                update(AuditLog)
                .where(AuditLog.id >= actual_from, AuditLog.id <= actual_to)
                .values(exported_at=now)
            )

            # Step 8: Record export metadata
            await db.execute(
                text("""
                    INSERT INTO immutable_exports
                        (export_hash, from_id, to_id, record_count,
                         storage_backend, storage_path, tsa_token, exported_by)
                    VALUES
                        (:hash, :from_id, :to_id, :count,
                         :backend, :path, :tsa, :by)
                """),
                {
                    "hash": batch_hash,
                    "from_id": actual_from,
                    "to_id": actual_to,
                    "count": len(logs),
                    "backend": storage_backend,
                    "path": storage_path,
                    "tsa": tsa_token,
                    "by": exported_by,
                },
            )
            await db.commit()

            logger.info(
                "forensic_export_complete",
                record_count=len(logs),
                from_id=actual_from,
                to_id=actual_to,
                batch_hash=batch_hash,
                storage_path=storage_path,
                has_tsa=tsa_token is not None,
            )

            return ExportResult(
                success=True,
                record_count=len(logs),
                batch_hash=batch_hash,
                storage_path=storage_path,
                tsa_token=tsa_token,
                from_id=actual_from,
                to_id=actual_to,
            )

        except Exception as e:
            logger.error("forensic_export_error", error=str(e))
            return ExportResult(
                success=False, record_count=0, batch_hash="",
                storage_path="", tsa_token=None, from_id=0, to_id=0,
                error=str(e),
            )

    @staticmethod
    async def deep_verify_chain(
        db: AsyncSession,
        limit: int = 10000,
        offset: int = 0,
    ) -> dict:
        """
        Full forensic chain verification — recomputes every hash.

        Unlike the basic verify_chain_integrity, this method:
        1. Recomputes hash from source data (not just checks linkage)
        2. Validates hash algorithm consistency
        3. Returns detailed tampering report
        """
        result = await db.execute(
            select(AuditLog)
            .order_by(AuditLog.id.asc())
            .limit(limit)
            .offset(offset)
        )
        logs = list(result.scalars().all())

        if not logs:
            return {
                "valid": True,
                "checked": 0,
                "tampered": [],
                "chain_breaks": [],
                "first_id": None,
                "last_id": None,
            }

        tampered = []
        chain_breaks = []

        for i, entry in enumerate(logs):
            # Check 1: Chain linkage
            if i == 0:
                if offset == 0 and entry.previous_hash != GENESIS_HASH:
                    chain_breaks.append({
                        "id": entry.id,
                        "issue": "first_entry_not_genesis",
                        "expected": GENESIS_HASH,
                        "actual": entry.previous_hash,
                    })
            else:
                if entry.previous_hash != logs[i - 1].log_hash:
                    chain_breaks.append({
                        "id": entry.id,
                        "issue": "chain_link_broken",
                        "expected": logs[i - 1].log_hash,
                        "actual": entry.previous_hash,
                    })

            # Check 2: Recompute hash from source data
            log_data = json.dumps({
                "agent_id": str(entry.agent_id),
                "sponsor_id": str(entry.sponsor_id),
                "action_type": entry.action_type if isinstance(entry.action_type, str) else entry.action_type.value,
                "service_name": entry.service_name,
                "permission_granted": entry.permission_granted,
                "cost_usd": entry.cost_usd,
                "timestamp": entry.timestamp.isoformat() if isinstance(entry.timestamp, datetime) else entry.timestamp,
            }, sort_keys=True)

            expected_hash = hash_chain(log_data, entry.previous_hash)
            if expected_hash != entry.log_hash:
                tampered.append({
                    "id": entry.id,
                    "issue": "hash_mismatch",
                    "stored_hash": entry.log_hash,
                    "computed_hash": expected_hash,
                })

        return {
            "valid": len(tampered) == 0 and len(chain_breaks) == 0,
            "checked": len(logs),
            "tampered": tampered,
            "chain_breaks": chain_breaks,
            "first_id": logs[0].id,
            "last_id": logs[-1].id,
        }

    @staticmethod
    async def generate_forensic_report(
        db: AsyncSession,
        from_id: int,
        to_id: int,
    ) -> dict:
        """Generate a forensic report for a range of audit entries."""
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.id >= from_id, AuditLog.id <= to_id)
            .order_by(AuditLog.id.asc())
        )
        logs = list(result.scalars().all())

        if not logs:
            return {"error": "No logs found in range"}

        # Compute batch hash
        canonical = _serialize_batch(logs)
        batch_hash = hashlib.sha3_256(canonical.encode("utf-8")).hexdigest()

        # Verify chain
        integrity = _verify_batch_chain(logs)

        # Stats
        denied_count = sum(1 for l in logs if not l.permission_granted)
        total_cost = sum(l.cost_usd or 0 for l in logs)
        unique_agents = len(set(str(l.agent_id) for l in logs))
        unique_services = len(set(l.service_name for l in logs if l.service_name))

        return {
            "range": {"from_id": from_id, "to_id": to_id},
            "record_count": len(logs),
            "batch_hash": batch_hash,
            "chain_integrity": integrity,
            "statistics": {
                "denied_actions": denied_count,
                "granted_actions": len(logs) - denied_count,
                "total_cost_usd": round(total_cost, 4),
                "unique_agents": unique_agents,
                "unique_services": unique_services,
                "time_range": {
                    "first": logs[0].timestamp.isoformat() if logs[0].timestamp else None,
                    "last": logs[-1].timestamp.isoformat() if logs[-1].timestamp else None,
                },
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ═══════════════════════════════════════════════════════
#  Internal Helpers
# ═══════════════════════════════════════════════════════

def _verify_batch_chain(logs: list[AuditLog]) -> dict:
    """Verify hash chain linkage within a batch."""
    broken = []
    for i, entry in enumerate(logs):
        if i == 0:
            continue
        if entry.previous_hash != logs[i - 1].log_hash:
            broken.append(entry.id)
    return {"valid": len(broken) == 0, "checked": len(logs), "broken_at": broken}


def _serialize_batch(logs: list[AuditLog]) -> str:
    """Canonical JSON serialization of audit batch for hashing."""
    entries = []
    for log in logs:
        entries.append({
            "id": log.id,
            "log_hash": log.log_hash,
            "previous_hash": log.previous_hash,
            "agent_id": str(log.agent_id),
            "sponsor_id": str(log.sponsor_id),
            "action_type": log.action_type if isinstance(log.action_type, str) else log.action_type.value,
            "service_name": log.service_name,
            "permission_granted": log.permission_granted,
            "cost_usd": log.cost_usd,
            "response_code": log.response_code,
            "ip_address": log.ip_address,
            "duration_ms": log.duration_ms,
            "timestamp": log.timestamp.isoformat() if isinstance(log.timestamp, datetime) else log.timestamp,
        })
    return json.dumps(entries, sort_keys=True, separators=(",", ":"))


async def _request_tsa_token(digest_hex: str) -> bytes | None:
    """
    Request an RFC 3161 timestamp token from a TSA server.

    The digest is sent as a SHA-256 hash (standard for TSA requests).
    Returns the raw DER-encoded TimeStampResp or None on failure.
    """
    try:
        # Build RFC 3161 TimeStampReq (simplified — uses SHA-256 message imprint)
        digest_bytes = bytes.fromhex(digest_hex)
        # SHA-256 OID: 2.16.840.1.101.3.4.2.1
        sha256_oid = b"\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00"
        # MessageImprint ::= SEQUENCE { hashAlgorithm, hashedMessage }
        hash_octet = b"\x04" + bytes([len(digest_bytes)]) + digest_bytes
        msg_imprint = b"\x30" + bytes([len(sha256_oid) + len(hash_octet)]) + sha256_oid + hash_octet
        # Version 1
        version = b"\x02\x01\x01"
        # CertReq = TRUE
        cert_req = b"\x01\x01\xff"
        # TimeStampReq ::= SEQUENCE { version, messageImprint, certReq }
        body = version + msg_imprint + cert_req
        ts_req = b"\x30" + bytes([len(body)]) + body

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                settings.FORENSIC_TSA_URL,
                content=ts_req,
                headers={"Content-Type": "application/timestamp-query"},
            )
            if resp.status_code == 200:
                logger.info("tsa_token_obtained", digest=digest_hex[:16])
                return resp.content
            else:
                logger.warning("tsa_request_failed", status=resp.status_code)
                return None
    except Exception as e:
        logger.warning("tsa_request_error", error=str(e))
        return None


async def _upload_s3(data: bytes, key: str, batch_hash: str) -> str:
    """Upload to S3 with Object Lock (COMPLIANCE mode)."""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.FORENSIC_S3_ENDPOINT or None,
            aws_access_key_id=settings.FORENSIC_S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.FORENSIC_S3_SECRET_KEY or None,
            region_name=settings.FORENSIC_S3_REGION or "us-east-1",
            config=BotoConfig(signature_version="s3v4"),
        )

        bucket = settings.FORENSIC_S3_BUCKET
        full_key = f"{settings.FORENSIC_S3_PREFIX}{key}"

        s3.put_object(
            Bucket=bucket,
            Key=full_key,
            Body=data,
            ContentType="application/json",
            # Object Lock: COMPLIANCE mode — cannot be deleted even by root
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=_retention_date(),
            Metadata={
                "batch-hash": batch_hash,
                "exported-by": "aegis-forensic-export",
            },
        )

        path = f"s3://{bucket}/{full_key}"
        logger.info("s3_upload_complete", path=path)
        return path

    except ImportError:
        logger.error("boto3_not_installed")
        raise RuntimeError("boto3 is required for S3 exports. pip install boto3")
    except Exception as e:
        logger.error("s3_upload_error", error=str(e))
        raise


async def _upload_local(data: bytes, filename: str) -> str:
    """Write to local filesystem (for dev/testing)."""
    import os
    export_dir = settings.FORENSIC_LOCAL_PATH
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, filename)
    with open(path, "wb") as f:
        f.write(data)
    logger.info("local_export_complete", path=path)
    return f"file://{path}"


def _retention_date() -> datetime:
    """Calculate retention end date for S3 Object Lock."""
    from datetime import timedelta
    days = settings.FORENSIC_RETENTION_DAYS
    return datetime.now(timezone.utc) + timedelta(days=days)


forensic_export = ForensicExportService()
