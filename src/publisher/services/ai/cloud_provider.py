"""Cloud AI API adapter supporting OpenAI, Gemini, and OpenAI-compatible endpoints."""

import json
import re
from typing import Any
import httpx
from src.publisher.core.logging_config import logger
from src.publisher.services.ai.base import (
    AIProviderError,
    EvidencePack,
    GeneratedDraftOutput,
    LLMProvider,
    PostPreferences,
)
from src.publisher.services.ai.prompts import build_generation_prompt, sanitize_linkedin_post


class CloudAPIProvider(LLMProvider):
    """Adapter for remote AI inference via standard REST APIs."""

    def __init__(
        self,
        api_key: str,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        timeout_seconds: float = 120.0,
    ):
        self.api_key = api_key
        self.provider = provider.lower()
        self.model = model
        self.timeout_seconds = timeout_seconds

        # Resolve base URL according to provider
        if base_url:
            self.base_url = base_url.rstrip("/")
        elif self.provider == "openrouter":
            self.base_url = "https://openrouter.ai/api/v1"
        elif self.provider == "gemini":
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        elif self.provider == "anthropic":
            # Direct or via compatibility layer
            self.base_url = "https://api.anthropic.com/v1"
        else:
            self.base_url = "https://api.openai.com/v1"

    def _get_headers(self) -> dict[str, str]:
        """Construct request headers with OpenRouter rankings metadata if applicable."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Build2Buzz/1.0",
        }
        if self.provider == "openrouter" or "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-OpenRouter-Title"] = "Build2Buzz"
            headers["X-Title"] = "Build2Buzz"
        return headers

    def validate_configuration(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "API key is required for Cloud AI provider."
        if not self.model or not self.model.strip():
            return False, "Model identifier is required."
        return True, ""

    async def test_connection(self) -> tuple[bool, str]:
        valid, msg = self.validate_configuration()
        if not valid:
            return False, msg

        endpoint = f"{self.base_url}/models"
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.get(endpoint, headers=headers)
                if res.status_code == 200:
                    return True, f"Successfully authenticated with {self.provider} API."
                elif res.status_code == 401:
                    return False, "Authentication failed (401 Unauthorized). Please check your API key."
                elif res.status_code == 403:
                    return False, f"Permission denied (403 Forbidden) for {self.provider} API."
                elif res.status_code == 404:
                    return False, f"Endpoint not found (404). Check API Base URL: {self.base_url}"
                else:
                    return False, f"Cloud provider returned status {res.status_code}: {res.text[:150]}"
        except Exception as exc:
            return False, f"Connection failed: {str(exc)}"

    async def generate_linkedin_draft(
        self, evidence: EvidencePack, preferences: PostPreferences
    ) -> GeneratedDraftOutput:
        valid, msg = self.validate_configuration()
        if not valid:
            raise AIProviderError(f"Cloud provider configuration error: {msg}")

        system_prompt, user_prompt = build_generation_prompt(evidence, preferences)
        endpoint = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }

        logger.info("Submitting draft generation request to cloud provider: %s (%s, timeout: %ds)", self.provider, self.model, int(self.timeout_seconds))
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(endpoint, headers=headers, json=payload)
                # Fallback: if custom or OpenRouter endpoint rejects response_format, retry without it
                if res.status_code == 400:
                    logger.info("Endpoint rejected response_format; retrying without it.")
                    payload_no_fmt = dict(payload)
                    payload_no_fmt.pop("response_format", None)
                    res = await client.post(endpoint, headers=headers, json=payload_no_fmt)

                if res.status_code == 401:
                    raise AIProviderError("Cloud API authentication failed (401 Unauthorized). Please verify or update your API key in AI Settings.")
                elif res.status_code == 404:
                    raise AIProviderError(f"Model '{self.model}' not found at {endpoint} (404). Check your Model Name and Base URL.")
                elif res.status_code != 200:
                    raise AIProviderError(
                        f"Cloud API request failed with status {res.status_code}: {res.text[:200]}"
                    )
                data = res.json()
        except httpx.TimeoutException:
            raise AIProviderError(
                f"Cloud API request timed out after {int(self.timeout_seconds)} seconds. "
                f"The remote model ('{self.model}') at '{self.base_url}' took too long to generate a response. "
                f"Consider using a faster model, checking your endpoint connectivity, or switching to Local GGUF mode."
            )
        except httpx.RequestError as exc:
            raise AIProviderError(f"Network error communicating with cloud AI: {exc}")

        # Parse raw content
        try:
            raw_content = data["choices"][0]["message"]["content"]
            # Clean markdown JSON fences if present
            cleaned_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.MULTILINE)
            try:
                parsed = json.loads(cleaned_json)
            except Exception:
                json_match = re.search(r"\{[\s\S]*\}", raw_content)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                else:
                    parsed = None
        except Exception as exc:
            raise AIProviderError(f"Failed to read model response: {exc}")

        if parsed and isinstance(parsed, dict) and "post_text" in parsed:
            raw_post = parsed.get("post_text", "").strip()
            hashtags = parsed.get("hashtags", [])
            project_links = parsed.get("project_links", [evidence.repo_url])
            evidence_refs = parsed.get("evidence_references", [])
            unverified_cautions = parsed.get("unverified_cautions", [])
        else:
            # Model generated plain text post directly
            raw_post = raw_content.strip()
            hashtags = re.findall(r"#\w+", raw_post)
            project_links = [evidence.repo_url]
            evidence_refs = ["README.md Repository Analysis"]
            unverified_cautions = []

        sanitized_post = sanitize_linkedin_post(
            raw_post,
            repo_url=evidence.repo_url,
            demo_url=evidence.demo_url,
            hashtag_prefs=preferences.hashtag_prefs,
        )

        # Construct output
        return GeneratedDraftOutput(
            post_text=sanitized_post,
            hashtags=hashtags or ["#Python", "#OpenSource"],
            project_links=project_links,
            evidence_references=evidence_refs,
            unverified_cautions=unverified_cautions,
        )

    def estimate_resources(self) -> dict[str, Any]:
        return {
            "provider_type": "cloud",
            "provider_name": self.provider,
            "model": self.model,
            "local_memory_required_mb": 0,
            "estimated_token_limit": 128000,
        }

    def close(self) -> None:
        pass
