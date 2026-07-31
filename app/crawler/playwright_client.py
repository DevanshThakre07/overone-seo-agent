"""Optional Playwright fetch for JS-heavy pages (stub until playwright extra installed)."""

from __future__ import annotations

from app.config.settings import PlaywrightSettings
from app.logging import get_logger

logger = get_logger(__name__)


class PlaywrightClient:
    def __init__(self, settings: PlaywrightSettings) -> None:
        self.settings = settings

    def fetch(self, url: str) -> str | None:
        if not self.settings.enabled:
            return None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright requested but not installed")
            return None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(
                url,
                timeout=self.settings.timeout_ms,
                wait_until=self.settings.wait_until,  # type: ignore[arg-type]
            )
            html = page.content()
            browser.close()
            return html
