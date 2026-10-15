"""Optional web research module for retrieving and fact-checking external documentation."""

from datetime import datetime, timezone
import re
from typing import Any
import httpx
from pydantic import BaseModel, Field
from src.publisher.core.logging_config import logger
from src.publisher.core.security import validate_safe_external_url
from src.publisher.services.ai.base import EvidenceItem


class WebResearchResult(BaseModel):
    """Structured result from an external web query or direct URL fetch."""

    query: str
    url: str
    title: str = ""
    snippet: str = ""
    source_provider: str = "none"
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WebResearchService:
    """Service handling optional live web research with strict rate-limiting and SSRF defenses."""

    def __init__(self, timeout_seconds: float = 12.0):
        self.timeout = timeout_seconds

    async def search(
        self,
        query: str,
        provider: str = "none",
        api_key: str | None = None,
        max_results: int = 3,
    ) -> list[WebResearchResult]:
        """Perform external web search using configured provider."""
        provider = (provider or "none").lower()

        if provider == "none" or not query or not query.strip():
            logger.info("Web research is disabled or query is empty.")
            return []

        if provider == "tavily":
            return await self._search_tavily(query, api_key, max_results)
        elif provider == "serpapi":
            return await self._search_serpapi(query, api_key, max_results)
        else:
            logger.warning("Unsupported or unknown search provider: %s", provider)
            return []

    async def _search_tavily(
        self, query: str, api_key: str | None, max_results: int
    ) -> list[WebResearchResult]:
        if not api_key:
            logger.warning("Tavily search enabled but no API key provided.")
            return []

        logger.info("Querying Tavily Search API for '%s'", query)
        endpoint = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(endpoint, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    results: list[WebResearchResult] = []
                    for item in data.get("results", []):
                        results.append(
                            WebResearchResult(
                                query=query,
                                url=item.get("url", ""),
                                title=item.get("title", ""),
                                snippet=item.get("content", "")[:600],
                                source_provider="tavily",
                            )
                        )
                    return results
                else:
                    logger.warning("Tavily returned status %d: %s", res.status_code, res.text[:100])
                    return []
        except Exception as exc:
            logger.warning("Tavily search request failed: %s", exc)
            return []

    async def _search_serpapi(
        self, query: str, api_key: str | None, max_results: int
    ) -> list[WebResearchResult]:
        if not api_key:
            logger.warning("SerpAPI search enabled but no API key provided.")
            return []

        logger.info("Querying SerpAPI for '%s'", query)
        endpoint = "https://serpapi.com/search.json"
        params = {
            "api_key": api_key,
            "q": query,
            "engine": "google",
            "num": max_results,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(endpoint, params=params)
                if res.status_code == 200:
                    data = res.json()
                    results: list[WebResearchResult] = []
                    for item in data.get("organic_results", [])[:max_results]:
                        results.append(
                            WebResearchResult(
                                query=query,
                                url=item.get("link", ""),
                                title=item.get("title", ""),
                                snippet=item.get("snippet", "")[:600],
                                source_provider="serpapi",
                            )
                        )
                    return results
                else:
                    logger.warning("SerpAPI returned status %d: %s", res.status_code, res.text[:100])
                    return []
        except Exception as exc:
            logger.warning("SerpAPI search request failed: %s", exc)
            return []

    async def fetch_url_content(self, url: str) -> WebResearchResult | None:
        """Fetch and extract text from a specific user-supplied research URL with SSRF protection."""
        is_safe, reason = validate_safe_external_url(url)
        if not is_safe:
            logger.warning("Rejected web research URL '%s' due to SSRF policy: %s", url, reason)
            return None

        logger.info("Fetching research content from URL: %s", url)
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                res = await client.get(url, headers={"User-Agent": "Build2BuzzResearcher/1.0"})
                if res.status_code != 200:
                    logger.warning("Failed to fetch research URL (%d): %s", res.status_code, url)
                    return None

                html = res.text
                title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""

                # Strip scripts, styles, and html tags
                clean_text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
                clean_text = re.sub(r"<[^>]+>", " ", clean_text)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()

                return WebResearchResult(
                    query=url,
                    url=url,
                    title=title,
                    snippet=clean_text[:1000],
                    source_provider="direct_url",
                )
        except Exception as exc:
            logger.warning("Error fetching research URL %s: %s", url, exc)
            return None

    @staticmethod
    def to_evidence_items(results: list[WebResearchResult]) -> list[EvidenceItem]:
        """Convert web research results into standard EvidenceItem records."""
        items: list[EvidenceItem] = []
        for r in results:
            if r.snippet:
                items.append(
                    EvidenceItem(
                        source_type="web_research",
                        content=f"External Web Fact ({r.title}): {r.snippet}",
                        category="general",
                        source_url=r.url,
                        verification_status="external",
                    )
                )
        return items
