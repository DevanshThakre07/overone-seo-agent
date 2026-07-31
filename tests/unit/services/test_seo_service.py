from pathlib import Path

import responses

from app.analyzers.registry import build_default_registry
from app.config.settings import CrawlSettings, Settings
from app.models.audit import AuditOptions
from app.services.crawler_service import CrawlerService
from app.services.seo_service import SeoService

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@responses.activate
def test_seo_service_returns_typed_audit():
    html = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/", body=html, status=200)
    responses.add(responses.GET, "https://example.com/sample", body=html, status=200)
    responses.add(responses.GET, "https://example.com/about", body=html, status=200)

    settings = Settings(
        crawl=CrawlSettings(
            max_pages=3,
            max_depth=1,
            delay_seconds=0,
            check_external_links=False,
        )
    )
    service = SeoService(
        settings=settings,
        crawler_service=CrawlerService(settings),
        registry=build_default_registry(),
    )
    audit = service.run_audit("https://example.com/", AuditOptions())
    assert audit.seed_url.startswith("https://example.com")
    assert audit.score >= 0
    assert audit.pages
    assert audit.analyzer_results
    assert "severity" in audit.summary
