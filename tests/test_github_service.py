"""Unit and integration tests for GitHub REST API integration."""

import base64
import pytest
import httpx
from unittest.mock import patch, MagicMock
from src.publisher.services.github_service import (
    GitHubClient,
    GitHubRepoInfo,
    GitHubServiceError,
    parse_github_url,
)


def test_parse_github_url_valid():
    """Verify standard GitHub URLs are correctly parsed into owner and repo."""
    assert parse_github_url("https://github.com/tiangolo/fastapi") == ("tiangolo", "fastapi")
    assert parse_github_url("https://github.com/psf/requests.git") == ("psf", "requests")
    assert parse_github_url("https://github.com/openai/openai-python/") == ("openai", "openai-python")
    assert parse_github_url("https://github.com/django/django/tree/main") == ("django", "django")


def test_parse_github_url_invalid():
    """Verify invalid or non-GitHub URLs raise GitHubServiceError."""
    with pytest.raises(GitHubServiceError, match="Invalid URL scheme"):
        parse_github_url("ftp://github.com/owner/repo")

    with pytest.raises(GitHubServiceError, match="URL host must be 'github.com'"):
        parse_github_url("https://gitlab.com/owner/repo")

    with pytest.raises(GitHubServiceError, match="Invalid GitHub repository URL path"):
        parse_github_url("https://github.com/onlyowner")

    with pytest.raises(GitHubServiceError):
        parse_github_url("not a url")


@pytest.mark.asyncio
async def test_fetch_repository_success_with_readme():
    """Verify fetching repository metadata and decoding base64 README."""
    sample_readme = "# Sample Project\nThis is a test project."
    encoded_readme = base64.b64encode(sample_readme.encode("utf-8")).decode("utf-8")

    meta_response = httpx.Response(
        status_code=200,
        json={
            "full_name": "octocat/Hello-World",
            "description": "My first repo",
            "html_url": "https://github.com/octocat/Hello-World",
            "default_branch": "master",
            "stargazers_count": 42,
            "forks_count": 5,
            "open_issues_count": 1,
            "topics": ["python", "ai"],
            "license": {"name": "MIT License"},
            "language": "Python",
        },
    )

    readme_response = httpx.Response(
        status_code=200,
        json={
            "name": "README.md",
            "content": encoded_readme,
            "encoding": "base64",
        },
    )

    async def mock_get(url, headers=None):
        if url.endswith("/readme"):
            return readme_response
        return meta_response

    client = GitHubClient()
    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        info = await client.fetch_repository("https://github.com/octocat/Hello-World")
        assert info.owner == "octocat"
        assert info.repo == "Hello-World"
        assert info.stars == 42
        assert info.has_readme is True
        assert info.readme_content == sample_readme
        assert info.license_name == "MIT License"


@pytest.mark.asyncio
async def test_fetch_repository_not_found():
    """Verify 404 response raises actionable GitHubServiceError."""
    not_found_response = httpx.Response(status_code=404, json={"message": "Not Found"})

    async def mock_get(url, headers=None):
        return not_found_response

    client = GitHubClient()
    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        with pytest.raises(GitHubServiceError, match="not found"):
            await client.fetch_repository("https://github.com/missing/repo")


@pytest.mark.asyncio
async def test_fetch_repository_rate_limited():
    """Verify 403 rate limit response gives clear troubleshooting message."""
    rate_limited_response = httpx.Response(
        status_code=403,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"},
        json={"message": "API rate limit exceeded"},
    )

    async def mock_get(url, headers=None):
        return rate_limited_response

    client = GitHubClient()
    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        with pytest.raises(GitHubServiceError, match="rate limit reached"):
            await client.fetch_repository("https://github.com/owner/repo")
