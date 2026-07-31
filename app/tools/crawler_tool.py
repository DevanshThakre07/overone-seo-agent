from __future__ import annotations

from app.models.crawl import CrawlStats
from app.services.crawler_service import CrawlerService


def crawl_site(url: str) -> CrawlStats:
    """Hermes-ready tool: crawl a site and return crawl stats."""
    _, stats = CrawlerService().crawl(url)
    return stats
