"""Controlled browser automation service for demo inspection using Playwright."""

from datetime import datetime, timezone
from pathlib import Path
import time
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel
from src.publisher.core.config import settings
from src.publisher.core.logging_config import logger
from src.publisher.core.security import validate_safe_external_url


class DemoObservation(BaseModel):
    """Structured observations extracted from inspecting a live demo."""

    url: str
    page_title: str = ""
    meta_description: str | None = None
    visible_text_snippet: str = ""
    screenshot_path: str | None = None
    load_success: bool = False
    status_code: int | None = None
    error_message: str | None = None
    inspected_at: str = ""


class DemoInspector:
    """Inspector executing controlled navigation to public demo URLs with SSRF protections."""

    def __init__(self, navigation_timeout_ms: int = 20000):
        self.timeout_ms = navigation_timeout_ms

    async def inspect(
        self,
        url: str,
        capture_screenshot: bool = True,
        project_id: int | None = None,
    ) -> DemoObservation:
        """Inspect a live demo page, extracting visible facts and a screenshot."""
        inspected_time = datetime.now(timezone.utc).isoformat()

        # Step 1: SSRF Pre-validation
        is_safe, reason = validate_safe_external_url(url)
        if not is_safe:
            logger.warning("Rejected demo URL '%s' due to SSRF policy: %s", url, reason)
            return DemoObservation(
                url=url,
                load_success=False,
                error_message=f"Security restriction: {reason}",
                inspected_at=inspected_time,
            )

        screenshot_file: str | None = None
        logger.info("Inspecting demo URL: %s", url)

        try:
            async with async_playwright() as p:
                # Launch Chromium in headless mode with sandboxing and resource restrictions
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
                try:
                    context = await browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Build2BuzzDemoInspector/1.0",
                        ignore_https_errors=False,  # Enforce valid certificates
                    )
                    page = await context.new_page()
                    page.set_default_timeout(self.timeout_ms)

                    # Intercept redirects to enforce SSRF policy on the target
                    async def handle_route(route, request):
                        req_url = request.url
                        safe, err = validate_safe_external_url(req_url)
                        if not safe:
                            logger.warning("Aborted navigation to redirected internal URL: %s (%s)", req_url, err)
                            await route.abort()
                            return
                        await route.continue_()

                    await page.route("**/*", handle_route)

                    response = await page.goto(
                        url, wait_until="domcontentloaded", timeout=self.timeout_ms
                    )
                    status_code = response.status if response else None

                    # Extract page title
                    title = await page.title()

                    # Extract meta description
                    meta_desc = await page.evaluate(
                        """() => {
                            const meta = document.querySelector('meta[name="description"]') || 
                                         document.querySelector('meta[property="og:description"]');
                            return meta ? meta.getAttribute('content') : null;
                        }"""
                    )

                    # Extract snippet of visible body text (up to 2000 chars)
                    body_text = await page.evaluate(
                        """() => {
                            return document.body ? document.body.innerText.replace(/\\s+/g, ' ').trim().slice(0, 2000) : '';
                        }"""
                    )

                    # Capture screenshot if requested
                    if capture_screenshot:
                        settings.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                        ts = int(time.time())
                        fname = f"demo_p{project_id or 'preview'}_{ts}.png"
                        out_path = settings.SCREENSHOTS_DIR / fname
                        await page.screenshot(path=str(out_path), full_page=False)
                        screenshot_file = str(out_path)

                    await context.close()

                    return DemoObservation(
                        url=url,
                        page_title=title or "",
                        meta_description=meta_desc,
                        visible_text_snippet=body_text or "",
                        screenshot_path=screenshot_file,
                        load_success=True,
                        status_code=status_code,
                        inspected_at=inspected_time,
                    )
                finally:
                    await browser.close()

        except PlaywrightTimeoutError:
            logger.warning("Demo navigation timed out after %d ms for %s", self.timeout_ms, url)
            return DemoObservation(
                url=url,
                load_success=False,
                error_message=f"Navigation timed out after {self.timeout_ms // 1000} seconds.",
                inspected_at=inspected_time,
            )
        except Exception as exc:
            logger.error("Failed to inspect demo %s: %s", url, exc)
            return DemoObservation(
                url=url,
                load_success=False,
                error_message=f"Failed to inspect demo: {str(exc)}",
                inspected_at=inspected_time,
            )
