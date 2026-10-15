"""Local GGUF LLM inference provider for private on-device generation."""

import json
import os
from pathlib import Path
import re
from typing import Any
from src.publisher.core.logging_config import logger
from src.publisher.services.ai.base import (
    AIProviderError,
    EvidencePack,
    GeneratedDraftOutput,
    LLMProvider,
    PostPreferences,
)
from src.publisher.services.ai.prompts import build_generation_prompt, sanitize_linkedin_post


class LocalLLMProvider(LLMProvider):
    """Adapter for local GGUF models executing via llama-cpp-python or local server."""

    def __init__(
        self,
        model_path: str,
        context_length: int = 4096,
        gpu_layers: int = 0,
    ):
        self.model_path = model_path
        self.context_length = context_length
        self.gpu_layers = gpu_layers
        self._model_instance: Any = None

    def validate_configuration(self) -> tuple[bool, str]:
        if not self.model_path or not self.model_path.strip():
            return False, "Model file path is required for Local LLM mode."

        p = Path(self.model_path)
        if not p.exists():
            return False, f"Model file not found at path: '{self.model_path}'"

        if p.suffix.lower() != ".gguf":
            return False, f"Unsupported model format '{p.suffix}'. Must be a valid .gguf file."

        if not p.is_file():
            return False, f"Specified model path is not a regular file: '{self.model_path}'"

        return True, ""

    def estimate_resources(self) -> dict[str, Any]:
        valid, msg = self.validate_configuration()
        if not valid:
            return {"valid": False, "error": msg}

        p = Path(self.model_path)
        size_bytes = p.stat().st_size
        size_gb = round(size_bytes / (1024**3), 2)

        # Estimate RAM requirement: model size + ~1GB context buffer
        estimated_ram_gb = round(size_gb + (self.context_length * 0.00025), 1)

        warning = None
        if size_gb > 8.0:
            warning = f"Model is large ({size_gb} GB). Ensure your system has at least {estimated_ram_gb} GB of available memory."

        return {
            "valid": True,
            "provider_type": "local",
            "model_path": str(p),
            "model_size_gb": size_gb,
            "estimated_ram_gb": estimated_ram_gb,
            "context_length": self.context_length,
            "gpu_layers": self.gpu_layers,
            "warning": warning,
        }

    async def test_connection(self) -> tuple[bool, str]:
        valid, msg = self.validate_configuration()
        if not valid:
            return False, msg

        resources = self.estimate_resources()
        return (
            True,
            f"GGUF model verified successfully. File size: {resources['model_size_gb']} GB. "
            f"Estimated memory footprint: {resources['estimated_ram_gb']} GB.",
        )

    def _get_or_load_model(self):
        """Load and cache the local Llama instance to avoid reloading between calls."""
        if self._model_instance is not None:
            return self._model_instance

        valid, msg = self.validate_configuration()
        if not valid:
            raise AIProviderError(f"Cannot load local model: {msg}")

        logger.info("Initializing local GGUF model: %s (ctx: %d, gpu: %d)", self.model_path, self.context_length, self.gpu_layers)

        try:
            from llama_cpp import Llama
            self._model_instance = Llama(
                model_path=self.model_path,
                n_ctx=self.context_length,
                n_gpu_layers=self.gpu_layers,
                verbose=False,
            )
            return self._model_instance
        except ImportError:
            raise AIProviderError(
                "llama-cpp-python is not installed in the virtual environment. "
                "Install it with compatible C++ build tools for your Windows hardware."
            )
        except Exception as exc:
            raise AIProviderError(f"Failed to load GGUF model '{self.model_path}': {str(exc)}")

    async def generate_linkedin_draft(
        self, evidence: EvidencePack, preferences: PostPreferences
    ) -> GeneratedDraftOutput:
        model = self._get_or_load_model()
        system_prompt, user_prompt = build_generation_prompt(evidence, preferences)

        logger.info("Running local inference for project: %s", evidence.project_name)
        try:
            response = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.25,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            raw_text = response["choices"][0]["message"]["content"]
            cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
            parsed = json.loads(cleaned_json)
        except Exception as exc:
            raise AIProviderError(f"Local model generation failed: {exc}")

        raw_post = parsed.get("post_text", "").strip()
        sanitized_post = sanitize_linkedin_post(
            raw_post,
            repo_url=evidence.repo_url,
            demo_url=evidence.demo_url,
            hashtag_prefs=preferences.hashtag_prefs,
        )

        return GeneratedDraftOutput(
            post_text=sanitized_post,
            hashtags=parsed.get("hashtags", []),
            project_links=parsed.get("project_links", [evidence.repo_url]),
            evidence_references=parsed.get("evidence_references", []),
            unverified_cautions=parsed.get("unverified_cautions", []),
        )

    def close(self) -> None:
        if self._model_instance is not None:
            logger.info("Releasing local GGUF model instance.")
            del self._model_instance
            self._model_instance = None
