"""Unit tests for security utilities and SSRF defenses."""

from src.publisher.core.security import mask_secret, validate_safe_external_url


def test_mask_secret():
    """Verify secrets are masked showing only last N characters."""
    assert mask_secret("") == ""
    assert mask_secret(None) == ""
    assert mask_secret("1234", show_last=4) == "••••"
    assert mask_secret("12345", show_last=4) == "•2345"
    sample = "sk-1234567890abcdef"
    assert mask_secret(sample, show_last=4) == ("•" * (len(sample) - 4)) + "cdef"


def test_reject_ssrf_and_localhost_urls():
    """Verify SSRF defenses reject loopback, internal IPs, and bad schemes."""
    # Loopback / localhost
    is_safe, msg = validate_safe_external_url("http://localhost:8000/secret")
    assert not is_safe
    assert "localhost" in msg.lower() or "prohibited" in msg.lower()

    is_safe, msg = validate_safe_external_url("http://127.0.0.1:8000")
    assert not is_safe

    # Cloud metadata
    is_safe, msg = validate_safe_external_url("http://169.254.169.254/latest/meta-data")
    assert not is_safe

    # File and ftp schemes
    is_safe, msg = validate_safe_external_url("file:///C:/Windows/win.ini")
    assert not is_safe
    assert "scheme" in msg.lower()

    is_safe, msg = validate_safe_external_url("ftp://ftp.example.com")
    assert not is_safe
