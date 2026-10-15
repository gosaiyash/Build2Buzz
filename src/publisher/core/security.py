"""Security utilities: secret redaction, safe URL checks, SSRF defenses."""

import ipaddress
import socket
from urllib.parse import urlparse


def mask_secret(secret: str | None, show_last: int = 4) -> str:
    """Mask a secret string for safe UI display (e.g., '••••••••abcd')."""
    if not secret:
        return ""
    if len(secret) <= show_last:
        return "•" * len(secret)
    return "•" * (len(secret) - show_last) + secret[-show_last:]


def is_ip_private_or_reserved(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is private, loopback, link-local, multicast, or reserved."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_safe_external_url(url: str) -> tuple[bool, str]:
    """Validate that a URL is safe to fetch/inspect externally (protects against SSRF).

    Strict rules:
    - Scheme must be http or https
    - Hostname must exist and not be empty
    - Hostname must not resolve to loopback, private, or link-local address
    - Disallowed ports (e.g. non-standard dangerous ports)
    """
    if not url or not isinstance(url, str):
        return False, "URL is required and must be a string."

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    if parsed.scheme.lower() not in {"http", "https"}:
        return False, f"Invalid scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname in URL."

    # Check for direct localhost aliases
    lower_host = hostname.lower()
    if lower_host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return False, f"Access to localhost/loopback address '{hostname}' is prohibited for security."

    # Prevent internal AWS/cloud metadata address
    if lower_host == "169.254.169.254" or lower_host.endswith(".internal"):
        return False, "Access to cloud metadata or internal network is prohibited."

    # Check port if specified
    if parsed.port:
        # Standard web ports or safe user ports
        if parsed.port in {21, 22, 23, 25, 135, 137, 138, 139, 445, 3389}:
            return False, f"Port {parsed.port} is blocked for security."

    # Resolve IP and verify it's not internal/private
    try:
        resolved_ips = socket.getaddrinfo(hostname, parsed.port or 80)
        for entry in resolved_ips:
            ip_str = entry[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            if is_ip_private_or_reserved(ip_obj):
                return False, f"Security violation: Resolved address '{ip_str}' is private or reserved."
    except socket.gaierror:
        # DNS failure - can't resolve
        return False, f"Could not resolve host '{hostname}' via DNS."
    except Exception as exc:
        return False, f"DNS resolution check failed: {exc}"

    return True, ""
