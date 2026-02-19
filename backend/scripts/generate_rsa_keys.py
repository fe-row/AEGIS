#!/usr/bin/env python3
"""
Generate RSA key pair for JWT RS256 signing.

Usage:
    python scripts/generate_rsa_keys.py

Outputs PEM-encoded keys ready to paste into .env (as single-line \\n-escaped strings).
"""
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def generate_rsa_keypair(key_size: int = 2048):
    """Generate an RSA private/public key pair."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    # PEM-encode private key (no passphrase)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # PEM-encode public key
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    return private_pem, public_pem


def to_env_value(pem: str) -> str:
    """Convert multi-line PEM to single-line for .env files."""
    return pem.replace("\n", "\\n")


if __name__ == "__main__":
    private_pem, public_pem = generate_rsa_keypair()

    print("=" * 60)
    print("RSA Key Pair Generated (2048-bit)")
    print("=" * 60)
    print()
    print("# Add these to your .env file:")
    print()
    print(f'JWT_PRIVATE_KEY="{to_env_value(private_pem)}"')
    print()
    print(f'JWT_PUBLIC_KEY="{to_env_value(public_pem)}"')
    print()
    print("JWT_ALGORITHM=RS256")
    print()
    print("=" * 60)
    print("IMPORTANT: Keep JWT_PRIVATE_KEY secret!")
    print("JWT_PUBLIC_KEY can be shared for token verification.")
    print("=" * 60)
