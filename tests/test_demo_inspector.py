"""Unit tests for Demo Inspector service and security defenses."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.publisher.services.demo_inspector import DemoInspector


@pytest.mark.asyncio
async def test_demo_inspector_rejects_ssrf_urls():
    """Verify demo inspector rejects local addresses without launching browser."""
    inspector = DemoInspector()
    obs = await inspector.inspect("http://127.0.0.1:8000")
    assert obs.load_success is False
    assert "Security restriction" in obs.error_message

    obs2 = await inspector.inspect("http://localhost:3000")
    assert obs2.load_success is False
    assert "Security restriction" in obs2.error_message


@pytest.mark.asyncio
async def test_demo_inspector_mocked_navigation():
    """Verify demo inspector extracts title, snippet, and screenshot when safe."""
    inspector = DemoInspector(navigation_timeout_ms=5000)

    mock_page = AsyncMock()
    mock_page.set_default_timeout = MagicMock()
    mock_page.title.return_value = "Awesome Project Demo"
    mock_page.evaluate.side_effect = [
        "A live interactive demonstration of AI algorithms.",  # meta description
        "Welcome to the interactive preview. Try features now.",  # body snippet
    ]
    mock_response = MagicMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_p = AsyncMock()
    mock_p.chromium.launch.return_value = mock_browser

    with patch("src.publisher.services.demo_inspector.validate_safe_external_url", return_value=(True, "")):
        with patch("src.publisher.services.demo_inspector.async_playwright") as mock_playwright:
            mock_playwright.return_value.__aenter__.return_value = mock_p

            obs = await inspector.inspect("https://example.com/demo", capture_screenshot=False)
            assert obs.load_success is True
            assert obs.page_title == "Awesome Project Demo"
            assert "interactive preview" in obs.visible_text_snippet
            assert obs.meta_description == "A live interactive demonstration of AI algorithms."
            assert obs.status_code == 200
