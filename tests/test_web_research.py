"""Unit tests for optional web research service."""

from unittest.mock import patch
import pytest
import httpx
from src.publisher.services.web_research import WebResearchResult, WebResearchService


@pytest.mark.asyncio
async def test_web_research_disabled_returns_empty():
    """Verify research returns empty list when provider is none."""
    service = WebResearchService()
    results = await service.search("FastAPI concurrent benchmarks", provider="none")
    assert results == []


@pytest.mark.asyncio
async def test_web_research_direct_url_rejects_ssrf():
    """Verify direct URL fetch rejects internal and loopback IP addresses."""
    service = WebResearchService()
    res = await service.fetch_url_content("http://127.0.0.1:8000/private")
    assert res is None


@pytest.mark.asyncio
async def test_web_research_tavily_mocked():
    """Verify Tavily search parsing with mock HTTP response."""
    service = WebResearchService()
    mock_resp = httpx.Response(
        status_code=200,
        json={
            "results": [
                {
                    "title": "FastAPI Documentation",
                    "url": "https://fastapi.tiangolo.com",
                    "content": "FastAPI framework, high performance, easy to learn, fast to code.",
                }
            ]
        },
    )

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        results = await service.search("FastAPI", provider="tavily", api_key="tvly-mock")
        assert len(results) == 1
        assert results[0].title == "FastAPI Documentation"
        assert results[0].source_provider == "tavily"

        evidence_items = service.to_evidence_items(results)
        assert len(evidence_items) == 1
        assert evidence_items[0].source_type == "web_research"
        assert evidence_items[0].verification_status == "external"
