from __future__ import annotations

from app.config.settings import Settings, get_settings
from app.crawler.crawler import WebsiteCrawler
from app.logging import get_logger
from app.models.crawl import CrawlResult, CrawlStats

logger = get_logger(__name__)


class CrawlerService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def crawl(self, url: str) -> tuple[list[CrawlResult], CrawlStats]:
        crawler = WebsiteCrawler(
            crawl_settings=self.settings.crawl,
            playwright_settings=self.settings.playwright,
        )
        try:
            return crawler.crawl(url)
        finally:
            crawler.close()
