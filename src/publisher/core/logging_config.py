"""Structured logging configuration with automatic secret redaction."""

import logging
import re
import sys
from typing import Any


# Patterns matching common sensitive tokens, bearer headers, api keys
SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE),
    re.compile(r"(api[_\-]?key\s*[:=]\s*['\"]?)[A-Za-z0-9_\-]{10,}['\"]?", re.IGNORECASE),
    re.compile(r"(token\s*[:=]\s*['\"]?)[A-Za-z0-9_\-]{10,}['\"]?", re.IGNORECASE),
    re.compile(r"(client[_\-]?secret\s*[:=]\s*['\"]?)[A-Za-z0-9_\-]{10,}['\"]?", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9]{20,})", re.IGNORECASE),
]


class RedactingFormatter(logging.Formatter):
    """Custom formatter that automatically masks API keys and secrets from log output."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        redacted = original
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        return redacted


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with redacting formatter and console output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = RedactingFormatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Clear existing handlers to prevent duplicate lines
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


logger = logging.getLogger("publisher")
