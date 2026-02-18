import pytest
from app.utils.crypto import (
    encrypt_secret, decrypt_secret, generate_identity_fingerprint,
    generate_ephemeral_token, generate_api_key, hash_api_key, hash_chain,
)


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        secret = "sk-abc123xyz789"
        encrypted = encrypt_secret(secret)
        assert encrypted != secret
        decrypted = decrypt_secret(encrypted)
        assert decrypted == secret

    def test_different_encryptions(self):
        secret = "same-secret"
        e1 = encrypt_secret(secret)
        e2 = encrypt_secret(secret)
        # Fernet uses random IV, so same plaintext → different ciphertext
        assert e1 != e2
        assert decrypt_secret(e1) == decrypt_secret(e2) == secret

    def test_decrypt_invalid(self):
        with pytest.raises(ValueError):
            decrypt_secret("not-a-valid-fernet-token")


class TestFingerprint:
    def test_unique_fingerprints(self):
        fp1 = generate_identity_fingerprint("bot1", "sponsor1")
        fp2 = generate_identity_fingerprint("bot1", "sponsor1")
        # Different because of random nonce
        assert fp1 != fp2

    def test_fingerprint_length(self):
        fp = generate_identity_fingerprint("test", "test")
        assert len(fp) == 64  # SHA3-256 hex


class TestAPIKey:
    def test_generate_and_hash(self):
        raw, hashed = generate_api_key()
        assert raw.startswith("aegis_")
        assert len(raw) > 20
        assert hash_api_key(raw) == hashed

    def test_hash_deterministic(self):
        key = "aegis_test_key_123"
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        assert h1 == h2


class TestHashChain:
    def test_chain_produces_different_hashes(self):
        h1 = hash_chain("data1", "0" * 64)
        h2 = hash_chain("data2", "0" * 64)
        assert h1 != h2

    def test_chain_depends_on_previous(self):
        h1 = hash_chain("same_data", "previous_a")
        h2 = hash_chain("same_data", "previous_b")
        assert h1 != h2

    def test_chain_is_deterministic(self):
        h1 = hash_chain("data", "prev")
        h2 = hash_chain("data", "prev")
        assert h1 == h2