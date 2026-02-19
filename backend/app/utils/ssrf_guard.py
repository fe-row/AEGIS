"""
SSRF Guard v4 — FIX: async DNS resolution, no event loop blocking.
"""
import asyncio
import ipaddress
import socket
import urllib.parse
from app.logging_config import get_logger

logger = get_logger("ssrf")

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

BLOCKED_HOSTNAMES = frozenset({
    "localhost", "metadata.google.internal",
    "metadata.google.com", "kubernetes.default.svc",
})


def _check_ip(ip_str: str) -> bool:
    """Returns True if IP is blocked."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in BLOCKED_NETWORKS)
    except ValueError:
        return False  # Not an IP address — handled by DNS check in caller


async def validate_url_async(url: str) -> tuple[bool, str, list[str]]:
    """Async SSRF validation — safe for event loop.
    Returns (is_safe, reason, resolved_ips).
    The caller should pin connections to resolved_ips to prevent DNS rebinding."""
    resolved_ips: list[str] = []
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "Malformed URL", []

    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked scheme: {parsed.scheme}", []

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname", []

    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False, f"Blocked hostname: {hostname}", []

    # Check if it's a raw IP
    try:
        if _check_ip(hostname):
            return False, f"Blocked IP: {hostname}", []
        return True, "OK", [hostname]
    except ValueError:
        pass

    # Async DNS resolution
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
        for family, type_, proto, canonname, sockaddr in infos:
            ip_str = sockaddr[0]
            if _check_ip(ip_str):
                logger.warning("ssrf_blocked", url=url, resolved_ip=ip_str)
                return False, f"Resolved to blocked IP: {ip_str}", []
            resolved_ips.append(ip_str)
    except socket.gaierror:
        return False, f"DNS failed: {hostname}", []
    except Exception as e:
        return False, f"Resolution error: {type(e).__name__}", []

    return True, "OK", resolved_ips


def validate_url_sync(url: str) -> tuple[bool, str]:
    """Synchronous version for Pydantic validators (basic checks only)."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "Malformed URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname"

    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False, f"Blocked: {hostname}"

    # Only check raw IPs synchronously — full DNS check happens async in proxy
    try:
        if _check_ip(hostname):
            return False, f"Blocked IP: {hostname}"
    except ValueError:
        pass

    return True, "OK"


# Alias for tests and backward compat
validate_url = validate_url_sync