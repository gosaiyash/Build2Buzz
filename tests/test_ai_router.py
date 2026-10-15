"""Unit tests for AI provider interfaces, prompts, and router isolation."""

import json
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from src.publisher.db.models import SettingsRecord
from src.publisher.services.ai.base import (
    AIProviderError,
    EvidenceItem,
    EvidencePack,
    PostPreferences,
)
from src.publisher.services.ai.cloud_provider import CloudAPIProvider
from src.publisher.services.ai.local_provider import LocalLLMProvider
from src.publisher.services.ai.prompts import build_generation_prompt
from src.publisher.services.ai.router import AIProviderRouter


def test_build_generation_prompt():
    """Verify prompt builder structures evidence and respects style."""
    evidence = EvidencePack(
        project_name="FastAPI-Starter",
        repo_url="https://github.com/example/starter",
        demo_url="https://demo.example.com",
        items=[
            EvidenceItem(
                source_type="readme",
                content="Modular architecture with dependency injection",
                category="feature",
                verification_status="documented",
            )
        ],
    )
    prefs = PostPreferences(style="developer", max_length=1500)
    system_p, user_p = build_generation_prompt(evidence, prefs)

    assert "STRICTLY" in system_p
    assert "DEVELOPER" in user_p
    assert "FastAPI-Starter" in user_p
    assert "Modular architecture" in user_p


def test_router_exclusive_cloud_mode():
    """Verify router instantiates CloudAPIProvider in cloud mode."""
    rec = SettingsRecord(
        active_ai_mode="cloud",
        cloud_provider="openai",
        cloud_model="gpt-4o-mini",
    )
    router = AIProviderRouter(rec, credential_resolver=lambda _: "test-sk")
    provider = router.get_active_provider()
    assert isinstance(provider, CloudAPIProvider)
    assert provider.model == "gpt-4o-mini"
    assert provider.api_key == "test-sk"


def test_router_exclusive_local_mode(tmp_path):
    """Verify router instantiates LocalLLMProvider in local mode."""
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"dummy gguf header")

    rec = SettingsRecord(
        active_ai_mode="local",
        local_model_path=str(model_file),
        local_context_length=2048,
        local_gpu_layers=0,
    )
    router = AIProviderRouter(rec)
    provider = router.get_active_provider()
    assert isinstance(provider, LocalLLMProvider)
    assert provider.model_path == str(model_file)
    assert provider.context_length == 2048


def test_router_rejects_unknown_mode():
    """Verify router strictly rejects unsupported modes with no silent fallback."""
    rec = SettingsRecord(active_ai_mode="quantum_ai")
    router = AIProviderRouter(rec)
    with pytest.raises(AIProviderError, match="Invalid AI mode"):
        router.get_active_provider()


def test_local_provider_validates_gguf_extension(tmp_path):
    """Verify LocalLLMProvider rejects non-gguf files."""
    bad_file = tmp_path / "model.bin"
    bad_file.write_bytes(b"data")

    provider = LocalLLMProvider(model_path=str(bad_file))
    valid, msg = provider.validate_configuration()
    assert not valid
    assert "Unsupported model format" in msg


@pytest.mark.asyncio
async def test_cloud_provider_mocked_generation():
    """Verify CloudAPIProvider makes request and parses structured output."""
    provider = CloudAPIProvider(api_key="test-key", provider="openai")

    mock_json_content = json.dumps({
        "post_text": "Announcing our new open-source project! Built with Python and FastAPI.",
        "hashtags": ["#Python", "#OpenSource"],
        "project_links": ["https://github.com/example/starter"],
        "evidence_references": ["README: Modular architecture"],
        "unverified_cautions": [],
    })

    mock_resp = httpx.Response(
        status_code=200,
        json={"choices": [{"message": {"content": mock_json_content}}]},
    )

    evidence = EvidencePack(
        project_name="TestProject",
        repo_url="https://github.com/example/starter",
        items=[],
    )
    prefs = PostPreferences()

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        output = await provider.generate_linkedin_draft(evidence, prefs)
        assert "Announcing our new open-source" in output.post_text
        assert "#Python" in output.hashtags
        assert output.project_links == ["https://github.com/example/starter"]


def test_sanitize_linkedin_post_zero_emojis_and_clean_links():
    """Verify sanitize_linkedin_post strips all emojis, converts markdown links, and attaches repo URL."""
    from src.publisher.services.ai.prompts import sanitize_linkedin_post

    raw_small_model_output = (
        "Discover the Portable Agent Skill for AI Coding Agents! 🛠️🌟\n"
        "Dive into the GitHub repository [here](https://github.com/gosaiyash/verified-engineer-skill) 🚀.\n"
        "* Key Feature 1\n"
        "* Key Feature 2\n"
        "#Python #OpenSource"
    )

    cleaned = sanitize_linkedin_post(
        raw_small_model_output,
        repo_url="https://github.com/gosaiyash/verified-engineer-skill",
    )

    # Check zero emojis
    assert "🛠" not in cleaned
    assert "🌟" not in cleaned
    assert "🚀" not in cleaned
    # Check no markdown link
    assert "[here]" not in cleaned
    assert "https://github.com/gosaiyash/verified-engineer-skill" in cleaned
    # Check bullet normalization
    assert "- Key Feature 1" in cleaned
    assert "- Key Feature 2" in cleaned

