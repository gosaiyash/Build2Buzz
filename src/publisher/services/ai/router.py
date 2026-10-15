"""Provider Router enforcing strict mutual exclusivity between Cloud and Local inference."""

from collections.abc import Callable
from typing import Any
from src.publisher.core.logging_config import logger
from src.publisher.db.models import SettingsRecord
from src.publisher.services.ai.base import AIProviderError, LLMProvider
from src.publisher.services.ai.cloud_provider import CloudAPIProvider
from src.publisher.services.ai.local_provider import LocalLLMProvider


class AIProviderRouter:
    """Router that resolves and instantiates strictly the single active AI provider."""

    def __init__(
        self,
        settings_record: SettingsRecord,
        credential_resolver: Callable[[str], str | None] | None = None,
    ):
        self.settings = settings_record
        self.credential_resolver = credential_resolver

    def get_active_provider(self) -> LLMProvider:
        """Resolve and instantiate the single active AI provider.

        Enforces:
        - Exactly one active mode ('cloud' or 'local').
        - Rejection of unknown modes.
        - ZERO silent fallback between providers.
        """
        mode = (self.settings.active_ai_mode or "cloud").lower().strip()

        if mode == "cloud":
            api_key = None
            if self.credential_resolver:
                api_key = self.credential_resolver("ai_api_key")
            api_key = api_key or ""

            timeout_sec = 120.0
            if self.settings.preferences and "cloud_timeout" in self.settings.preferences:
                try:
                    timeout_sec = float(self.settings.preferences["cloud_timeout"])
                except (ValueError, TypeError):
                    timeout_sec = 120.0

            return CloudAPIProvider(
                api_key=api_key,
                provider=self.settings.cloud_provider,
                model=self.settings.cloud_model,
                base_url=self.settings.cloud_base_url,
                timeout_seconds=timeout_sec,
            )

        elif mode == "local":
            if not self.settings.local_model_path:
                raise AIProviderError(
                    "Local LLM mode is active, but no GGUF model path has been configured in Settings."
                )

            return LocalLLMProvider(
                model_path=self.settings.local_model_path,
                context_length=self.settings.local_context_length,
                gpu_layers=self.settings.local_gpu_layers,
            )

        else:
            raise AIProviderError(
                f"Invalid AI mode '{mode}'. Mode must be strictly either 'cloud' or 'local'."
            )
