import pytest
from app.utils.ssrf_guard import validate_url


class TestSSRFGuard:
    def test_public_url_allowed(self):
        safe, reason = validate_url("https://api.openai.com/v1/chat")
        assert safe is True

    def test_localhost_blocked(self):
        safe, reason = validate_url("http://localhost:8080/admin")
        assert safe is False
        assert "Blocked" in reason

    def test_127_blocked(self):
        safe, reason = validate_url("http://127.0.0.1:9090/")
        assert safe is False

    def test_private_10_blocked(self):
        safe, reason = validate_url("http://10.0.0.1/internal")
        assert safe is False

    def test_private_172_blocked(self):
        safe, reason = validate_url("http://172.16.0.1/internal")
        assert safe is False

    def test_private_192_blocked(self):
        safe, reason = validate_url("http://192.168.1.1/admin")
        assert safe is False

    def test_aws_metadata_blocked(self):
        safe, reason = validate_url("http://169.254.169.254/latest/meta-data/")
        assert safe is False

    def test_metadata_google_blocked(self):
        safe, reason = validate_url("http://metadata.google.internal/computeMetadata/v1/")
        assert safe is False

    def test_ftp_blocked(self):
        safe, reason = validate_url("ftp://files.internal/data")
        assert safe is False
        assert "scheme" in reason.lower()

    def test_no_hostname(self):
        safe, reason = validate_url("http:///path")
        assert safe is False

    def test_valid_https(self):
        safe, reason = validate_url("https://api.stripe.com/v1/charges")
        assert safe is True