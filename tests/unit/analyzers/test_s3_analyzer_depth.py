"""S3 analyzer depth — internal link graph + richer schema checks."""

from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.analyzers.links_analyzer import LinksAnalyzer
from app.analyzers.schema_analyzer import SchemaAnalyzer
from app.config.settings import AnalyzerSettings
from app.extractor.html_extractor import HtmlExtractor
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


def _page(
    url: str,
    *,
    internal: list[str] | None = None,
    schema_types: list[str] | None = None,
    has_json_ld: bool = False,
    parse_errors: int = 0,
    blocks: list | None = None,
) -> PageExtraction:
    return PageExtraction(
        url=url,
        final_url=url,
        status_code=200,
        title="T",
        h1=["H"],
        word_count=40,
        internal_links=internal or [],
        schema_types=schema_types or [],
        has_json_ld=has_json_ld or bool(schema_types),
        json_ld_parse_errors=parse_errors,
        json_ld_blocks=blocks or [],
    )


def test_links_graph_detects_orphan_and_metrics():
    seed = "https://example.com/"
    pages = [
        _page(seed, internal=["https://example.com/a"]),
        _page("https://example.com/a", internal=["https://example.com/"]),
        _page("https://example.com/orphan", internal=["https://example.com/"]),
    ]
    result = LinksAnalyzer().analyze(_ctx(pages, seed=seed))
    codes = {i.code for i in result.issues}
    assert "orphan_page" in codes
    assert result.metrics["graph_nodes"] == 3
    assert result.metrics["orphan_pages"] == 1
    assert result.metrics["graph_edges"] >= 2


def test_links_graph_small_crawl_skips_orphan_signal():
    seed = "https://example.com/"
    pages = [_page(seed, internal=[])]
    result = LinksAnalyzer().analyze(_ctx(pages, seed=seed))
    assert result.metrics["graph_nodes"] == 1
    assert result.metrics["orphan_pages"] == 0
    assert "orphan" in (result.metrics.get("graph_note") or "").lower()
    assert not any(i.code == "orphan_page" for i in result.issues)


def test_schema_parse_error_and_homepage_types():
    seed = "https://example.com/"
    pages = [
        _page(
            seed,
            schema_types=["WebPage"],
            has_json_ld=True,
            blocks=[
                {
                    "ok": True,
                    "types": ["WebPage"],
                    "props": {
                        "objects": [{"types": ["WebPage"], "props": {"name": "Home"}}]
                    },
                }
            ],
        ),
        _page(
            "https://example.com/broken-json",
            has_json_ld=False,
            parse_errors=1,
            blocks=[{"ok": False, "types": [], "error": "Expecting value"}],
        ),
    ]
    result = SchemaAnalyzer().analyze(_ctx(pages, seed=seed))
    codes = {i.code for i in result.issues}
    assert "schema_parse_error" in codes
    assert "missing_organization_schema" in codes
    assert "missing_website_schema" in codes
    assert result.metrics["seed_has_organization"] is False
    assert result.metrics["seed_has_website"] is False


def test_schema_empty_required_field():
    seed = "https://example.com/"
    pages = [
        _page(
            seed,
            schema_types=["Organization", "WebSite"],
            has_json_ld=True,
            blocks=[
                {
                    "ok": True,
                    "types": ["Organization"],
                    "props": {
                        "objects": [
                            {"types": ["Organization"], "props": {"name": ""}}
                        ]
                    },
                }
            ],
        )
    ]
    result = SchemaAnalyzer().analyze(_ctx(pages, seed=seed))
    assert any(i.code == "schema_empty_required" for i in result.issues)


def test_extractor_records_json_ld_parse_errors():
    html = """
    <html><head>
      <script type="application/ld+json">{not-json</script>
      <script type="application/ld+json">
      {"@type":"Organization","name":"Acme"}
      </script>
    </head><body><h1>Hi</h1><a href="/about">About</a></body></html>
    """
    crawl = CrawlResult(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        html=html,
        content_length=len(html),
        redirect_chain=[],
        depth=0,
        is_broken=False,
        js_rendered=False,
    )
    page = HtmlExtractor().extract(crawl, "https://example.com/")
    assert page.json_ld_parse_errors >= 1
    assert "Organization" in page.schema_types
    assert page.json_ld_script_count == 2
    assert any(not b.get("ok") for b in page.json_ld_blocks)
    assert any(b.get("ok") for b in page.json_ld_blocks)
