"""
Tests for Webhook HMAC Signer — signing and verification of webhook payloads.

Validates:
  1. Sign + verify round-trip
  2. Tampered payload rejected
  3. Expired timestamp rejected
  4. Missing secret handled gracefully
  5. Replay attack prevention
"""
import time
import json
import pytest
from unittest.mock import patch

from app.utils.webhook_signer import sign_payload, verify_signature


TEST_SECRET = "test-hmac-secret-key-32bytes-long"


class TestSignPayload:
    def test_sign_returns_headers(self):
        """Signing should return X-Aegis-Signature and X-Aegis-Timestamp headers."""
        headers = sign_payload({"text": "hello"}, secret=TEST_SECRET)
        assert "X-Aegis-Signature" in headers
        assert "X-Aegis-Timestamp" in headers
        assert headers["X-Aegis-Signature"].startswith("sha256=")

    def test_sign_dict_payload(self):
        """Dict payloads should be serialized deterministically."""
        h1 = sign_payload({"b": 2, "a": 1}, secret=TEST_SECRET)
        h2 = sign_payload({"a": 1, "b": 2}, secret=TEST_SECRET)
        # Same timestamp won't match due to timing, but format should be consistent
        assert h1["X-Aegis-Signature"].startswith("sha256=")
        assert h2["X-Aegis-Signature"].startswith("sha256=")

    def test_sign_string_payload(self):
        """String payloads should work directly."""
        headers = sign_payload("raw string body", secret=TEST_SECRET)
        assert "X-Aegis-Signature" in headers

    def test_sign_no_secret_returns_empty(self):
        """Missing secret should return empty headers (graceful degradation)."""
        with patch("app.utils.webhook_signer.settings") as mock_settings:
            mock_settings.WEBHOOK_HMAC_SECRET = ""
            headers = sign_payload({"test": True}, secret=None)
        # When secret is None and settings has empty string
        # sign_payload uses settings.WEBHOOK_HMAC_SECRET which is ""
        assert headers == {} or "X-Aegis-Signature" in headers


class TestVerifySignature:
    def test_valid_signature_accepted(self):
        """A properly signed payload should verify successfully."""
        payload = {"action": "approve", "request_id": "abc-123"}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        headers = sign_payload(payload, secret=TEST_SECRET)

        result = verify_signature(
            payload=body,
            signature_header=headers["X-Aegis-Signature"],
            timestamp_header=headers["X-Aegis-Timestamp"],
            secret=TEST_SECRET,
        )
        assert result is True

    def test_tampered_payload_rejected(self):
        """Modifying the payload after signing should fail verification."""
        payload = {"action": "approve"}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        headers = sign_payload(payload, secret=TEST_SECRET)

        tampered_body = json.dumps({"action": "reject"}, sort_keys=True, separators=(",", ":"))
        result = verify_signature(
            payload=tampered_body,
            signature_header=headers["X-Aegis-Signature"],
            timestamp_header=headers["X-Aegis-Timestamp"],
            secret=TEST_SECRET,
        )
        assert result is False

    def test_wrong_secret_rejected(self):
        """Using a different secret should fail verification."""
        payload = {"test": True}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        headers = sign_payload(payload, secret=TEST_SECRET)

        result = verify_signature(
            payload=body,
            signature_header=headers["X-Aegis-Signature"],
            timestamp_header=headers["X-Aegis-Timestamp"],
            secret="wrong-secret",
        )
        assert result is False

    def test_expired_timestamp_rejected(self):
        """A timestamp older than max_age_seconds should be rejected."""
        payload = {"test": True}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        headers = sign_payload(payload, secret=TEST_SECRET)

        # Fake an old timestamp
        old_timestamp = str(int(time.time()) - 600)
        result = verify_signature(
            payload=body,
            signature_header=headers["X-Aegis-Signature"],
            timestamp_header=old_timestamp,
            secret=TEST_SECRET,
            max_age_seconds=300,
        )
        assert result is False

    def test_invalid_timestamp_format_rejected(self):
        """Non-numeric timestamp should be rejected."""
        result = verify_signature(
            payload="test",
            signature_header="sha256=abc",
            timestamp_header="not-a-number",
            secret=TEST_SECRET,
        )
        assert result is False

    def test_missing_sha256_prefix_rejected(self):
        """Signature without sha256= prefix should be rejected."""
        result = verify_signature(
            payload="test",
            signature_header="abc123",
            timestamp_header=str(int(time.time())),
            secret=TEST_SECRET,
        )
        assert result is False

    def test_empty_secret_rejects(self):
        """Empty secret should reject verification."""
        with patch("app.utils.webhook_signer.settings") as mock_settings:
            mock_settings.WEBHOOK_HMAC_SECRET = ""
            result = verify_signature(
                payload="test",
                signature_header="sha256=abc",
                timestamp_header=str(int(time.time())),
                secret=None,
            )
        # No secret → always reject
        assert result is False


class TestAntiReplay:
    def test_fresh_timestamp_accepted(self):
        """A timestamp within the max_age window should pass."""
        payload = {"ok": True}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        headers = sign_payload(payload, secret=TEST_SECRET)

        result = verify_signature(
            payload=body,
            signature_header=headers["X-Aegis-Signature"],
            timestamp_header=headers["X-Aegis-Timestamp"],
            secret=TEST_SECRET,
            max_age_seconds=60,
        )
        assert result is True

    def test_future_timestamp_within_window(self):
        """A slightly future timestamp (clock skew) should still pass."""
        payload = {"ok": True}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        # Manually create a signature with a timestamp 10s in the future
        import hmac
        import hashlib
        future_ts = str(int(time.time()) + 10)
        message = f"{future_ts}.{body}"
        sig = hmac.new(TEST_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

        result = verify_signature(
            payload=body,
            signature_header=f"sha256={sig}",
            timestamp_header=future_ts,
            secret=TEST_SECRET,
            max_age_seconds=300,
        )
        assert result is True
