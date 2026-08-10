"""Agent-quality: real robots.txt, stronger canonicals, quieter schema/links."""

from __future__ import annotations

import responses

from app.analyzers.base import AnalysisContext
from app.analyzers.canonical_analyzer import CanonicalAnalyzer
from app.analyzers.links_analyzer import LinksAnalyzer
from app.analyzers.robots_analyzer import RobotsAnalyzer
from app.analyzers.schema_analyzer import SchemaAnalyzer
from app.analyzers.scorer import INFORMATIONAL_ONLY_CODES
from app.config.settings import AnalyzerSettings
from app.crawler.robots_fetch import fetch_robots_snapshot
from app.models.crawl import CrawlResult, CrawlStats
from app.models.page import PageExtraction


def _ctx(pages: list[PageExtraction], *, seed: str = "https://example.com/") -> AnalysisContext:
    return AnalysisContext(
        seed_url=seed,
        pages=pages,
        crawl_stats=CrawlStats(seed_url=seed, pages_crawled=len(pages)),
        config=AnalyzerSettings(),
        crawl_results=[],
    )


@responses.activate
def test_fetch_robots_disallow_all():
    from app.crawler.client import HttpClient

    body = "User-agent: *\nDisallow: /\n"
    responses.add(responses.GET, "https://example.com/robots.txt", body=body, status=200)
    client = HttpClient(user_agent="seo-agent-test", timeout=5.0, max_redirects=3)
    try:
        snap = fetch_robots_snapshot("https://example.com/", client, user_agent="seo-agent-test")
    finally:
        client.close()
    assert snap["status"] == "ok"
    assert snap["disallow_all"] is True


@responses.activate
def test_robots_analyzer_missing_and_meta_noindex(monkeypatch):
    monkeypatch.setenv("SEO_STORAGE_PATH", "/tmp/seo-test-robots.db")
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()

    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    pages = [
        PageExtraction(
            url="https://example.com/",
            final_url="https://example.com/",
            robots_meta="noindex, nofollow",
        )
    ]
    result = RobotsAnalyzer().analyze(_ctx(pages))
    codes = {i.code for i in result.issues}
    assert "robots_missing" in codes
    assert "robots_noindex" in codes
    seed_noindex = next(i for i in result.issues if i.code == "robots_noindex")
    assert seed_noindex.severity.value == "warning"
    assert result.metrics["robots_txt_status"] == "missing"
    settings_module.get_settings.cache_clear()


def test_canonical_cross_host_and_seed_missing():
    pages = [
        PageExtraction(
            url="https://example.com/",
            final_url="https://example.com/",
            canonical=None,
        ),
        PageExtraction(
            url="https://example.com/a",
            final_url="https://example.com/a",
            canonical="https://other.com/a",
        ),
    ]
    result = CanonicalAnalyzer().analyze(_ctx(pages))
    codes = {i.code for i in result.issues}
    assert "missing_canonical" in codes
    assert "canonical_cross_host" in codes
    missing = next(i for i in result.issues if i.code == "missing_canonical")
    assert missing.severity.value == "warning"


def test_schema_aggregates_instead_of_per_page_spam():
    pages = [
        PageExtraction(
            url=f"https://example.com/p{i}",
            final_url=f"https://example.com/p{i}",
            has_json_ld=False,
        )
        for i in range(8)
    ]
    pages[0] = PageExtraction(
        url="https://example.com/",
        final_url="https://example.com/",
        has_json_ld=False,
    )
    result = SchemaAnalyzer().analyze(_ctx(pages, seed="https://example.com/"))
    codes = [i.code for i in result.issues]
    assert codes.count("missing_schema") <= 1
    assert "schema_coverage_low" in codes
    # Must not emit one missing_schema per page.
    assert len([c for c in codes if c == "missing_schema"]) == 1
    assert result.metrics["pages_missing_schema"] == 8


def test_broken_external_capped_and_unscored():
    crawl_results = [
        CrawlResult(
            url=f"https://out.example/x{i}",
            final_url=f"https://out.example/x{i}",
            status_code=404,
            error="HTTP 404",
            depth=-1,
        )
        for i in range(12)
    ]
    ctx = _ctx(
        [
            PageExtraction(
                url="https://example.com/",
                final_url="https://example.com/",
                title="Home",
            )
        ]
    )
    ctx.crawl_results = crawl_results
    result = LinksAnalyzer().analyze(ctx)
    broken = [i for i in result.issues if i.code == "broken_external_link"]
    assert len(broken) == 5
    assert any(i.code == "broken_external_link_summary" for i in result.issues)
    assert result.metrics["broken_external_links"] == 12
    assert "broken_external_link" in INFORMATIONAL_ONLY_CODES
