from __future__ import annotations

from typing import Any

from app.config.settings import Settings, get_settings
from app.crawler.auth import CrawlAuth, detect_login_wall
from app.crawler.client import HttpClient
from app.crawler.crawler import WebsiteCrawler
from app.logging import get_logger, log_event
from app.models.crawl import CrawlResult, CrawlStats
from app.utils.url import normalize_url

logger = get_logger(__name__)


class CrawlerService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def crawl(
        self,
        url: str,
        *,
        auth: CrawlAuth | None = None,
    ) -> tuple[list[CrawlResult], CrawlStats]:
        """BFS crawl using GET/HEAD only. Auth (if any) is in-memory for this call."""
        crawler = WebsiteCrawler(
            crawl_settings=self.settings.crawl,
            playwright_settings=self.settings.playwright,
            auth=auth,
        )
        try:
            return crawler.crawl(url)
        finally:
            crawler.close()

    def probe_login_wall(self, url: str) -> dict[str, Any]:
        """Dry-run: public GET of the seed URL (no credentials) + login-wall heuristics.

        Never attaches cookies/headers. Safe to call before opting into authenticated crawl.
        """
        seed = normalize_url(url)
        log_event(logger, "login_wall_probe_started", url=seed, authenticated=False)
        client = HttpClient(
            user_agent=self.settings.crawl.user_agent,
            timeout=self.settings.crawl.timeout_seconds,
            max_redirects=self.settings.crawl.max_redirects,
            auth=None,
        )
        try:
            fetch = client.get(seed)
            wall = detect_login_wall(
                url=seed,
                final_url=fetch.final_url,
                status_code=fetch.status_code or None,
                html=fetch.text or None,
            )
            wall["live_fetch"] = {
                "ok": not bool(fetch.error) and bool(fetch.status_code),
                "status_code": fetch.status_code,
                "final_url": fetch.final_url,
                "error": fetch.error,
                "authenticated": False,
            }
            log_event(
                logger,
                "login_wall_probe_completed",
                url=seed,
                requires_login=wall.get("requires_login"),
                signals=wall.get("signals"),
            )
            return wall
        finally:
            client.close()
