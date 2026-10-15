"""Application configuration management using Pydantic Settings."""

from pathlib import Path
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings schema strictly enforcing localhost binding and secure defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "GitHub LinkedIn AI Publisher"
    APP_VERSION: str = "1.0.1"
    APP_ENV: Literal["development", "production", "testing"] = "development"
    DEBUG: bool = False

    # Strictly localhost
    HOST: str = Field(default="127.0.0.1", description="Strictly bind to localhost")
    PORT: int = Field(default=8000, description="Local port")

    # Storage paths
    DATA_DIR: Path = Field(default=Path("./data"))
    SCREENSHOTS_DIR: Path = Field(default=Path("./data/screenshots"))
    DATABASE_URL: str = Field(default="sqlite:///./data/publisher.db")

    # Active AI inference mode: strictly mutually exclusive
    DEFAULT_AI_MODE: Literal["cloud", "local"] = "cloud"

    # LinkedIn App non-secret settings
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_REDIRECT_URI: str = "http://127.0.0.1:8000/api/integrations/linkedin/callback"
    LINKEDIN_API_VERSION: str = Field(
        default="",
        description="LinkedIn REST API monthly version (YYYYMM). Defaults dynamically to current active version if empty.",
    )

    # Web Research Settings
    DEFAULT_SEARCH_PROVIDER: Literal["none", "tavily", "serpapi", "duckduckgo"] = "none"
    SEARCH_ENABLED: bool = False

    @field_validator("HOST")
    @classmethod
    def validate_localhost_binding(cls, v: str) -> str:
        """Enforce that server binds only to localhost to protect user machine."""
        allowed_hosts = {"127.0.0.1", "localhost", "::1"}
        if v not in allowed_hosts:
            raise ValueError(
                f"Security violation: Application must bind to localhost only ({allowed_hosts}), got '{v}'"
            )
        return v

    def ensure_directories(self) -> None:
        """Ensure necessary local data directories exist."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# Global settings singleton
settings = Settings()
settings.ensure_directories()


def get_current_linkedin_api_version() -> str:
    """Return active LinkedIn API version in YYYYMM format.

    LinkedIn enforces monthly versioning and deactivates versions after 12 months.
    If LINKEDIN_API_VERSION is configured in settings or environment, it is used.
    Otherwise, automatically generates an active version based on UTC date:
    - If early in month (days 1-6), uses previous month to avoid unreleased version errors.
    - Otherwise uses current month YYYYMM.
    """
    from datetime import datetime, timezone

    if settings.LINKEDIN_API_VERSION and settings.LINKEDIN_API_VERSION.strip():
        return settings.LINKEDIN_API_VERSION.strip()

    now = datetime.now(timezone.utc)
    if now.day < 7:
        if now.month == 1:
            return f"{now.year - 1}12"
        return f"{now.year}{now.month - 1:02d}"
    return f"{now.year}{now.month:02d}"


def get_fallback_linkedin_api_version(current_ver: str) -> str:
    """Return an alternative active version (1 month prior) if the primary version encounters 426."""
    from datetime import datetime, timezone

    try:
        clean = current_ver.strip()
        year = int(clean[:4])
        month = int(clean[4:6])
        if month == 1:
            return f"{year - 1}12"
        return f"{year}{month - 1:02d}"
    except Exception:
        now = datetime.now(timezone.utc)
        if now.month == 1:
            return f"{now.year - 1}12"
        return f"{now.year}{now.month - 1:02d}"

