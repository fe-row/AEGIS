#!/bin/sh
# Generate self-signed TLS certificate for local development.
# For production, use Let's Encrypt / Certbot instead.

CERT_DIR="$(dirname "$0")/ssl"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    echo "✅ Certificates already exist at $CERT_DIR"
    exit 0
fi

echo "🔐 Generating self-signed TLS certificate..."

openssl req -x509 -nodes -days 365 \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" \
    -subj "/C=AR/ST=Local/L=Dev/O=AEGIS/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:*.aegis.dev,IP:127.0.0.1"

echo "✅ Certificate generated at $CERT_DIR/"
echo "   Valid for: 365 days"
echo "   SANs: localhost, *.aegis.dev, 127.0.0.1"
