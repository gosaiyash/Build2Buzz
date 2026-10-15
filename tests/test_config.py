"""Unit tests for configuration validation and localhost constraints."""

import pytest
from pydantic import ValidationError
from src.publisher.core.config import Settings


def test_default_settings_binds_to_localhost():
    """Verify that default settings strictly bind to 127.0.0.1."""
    config = Settings()
    assert config.HOST in {"127.0.0.1", "localhost"}
    assert config.PORT == 8000
    assert config.DEFAULT_AI_MODE == "cloud"


def test_reject_external_host_binding():
    """Verify that setting HOST to an external or wildcard IP raises ValidationError."""
    with pytest.raises(ValidationError):
        Settings(HOST="0.0.0.0")

    with pytest.raises(ValidationError):
        Settings(HOST="192.168.1.50")

    with pytest.raises(ValidationError):
        Settings(HOST="example.com")
