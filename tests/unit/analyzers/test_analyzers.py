from app.analyzers.base import AnalysisContext
from app.analyzers.headings_analyzer import HeadingsAnalyzer
from app.analyzers.image_alt_analyzer import ImageAltAnalyzer
from app.analyzers.links_analyzer import LinksAnalyzer
from app.analyzers.meta_description_analyzer import MetaDescriptionAnalyzer
from app.analyzers.metrics import build_structured_seo_metrics
from app.analyzers.page_size_analyzer import PageSizeAnalyzer
from app.analyzers.registry import build_default_registry
from app.analyzers.title_analyzer import TitleAnalyzer
from app.config.settings import AnalyzerSettings
from app.models.crawl import CrawlStats
from app.models.page import ImageInfo, PageExtraction


def _ctx(pages: list[PageExtraction]) -> AnalysisContext:
    return AnalysisContext(
        seed_url="https://example.com",
        pages=pages,
        crawl_stats=CrawlStats(seed_url="https://example.com", pages_crawled=len(pages)),
        config=AnalyzerSettings(),
    )


def test_title_missing_and_duplicate():
    pages = [
        PageExtraction(url="https://example.com/a", final_url="https://example.com/a", title=None),
        PageExtraction(
            url="https://example.com/b", final_url="https://example.com/b", title="Same Title Value Across Pages Here"
        ),
        PageExtraction(
            url="https://example.com/c", final_url="https://example.com/c", title="Same Title Value Across Pages Here"
        ),
    ]
    result = TitleAnalyzer().analyze(_ctx(pages))
    codes = {i.code for i in result.issues}
    assert "missing_title" in codes
    assert "duplicate_title" in codes
    assert result.metrics["pages_with_title"] == 2


def test_meta_and_headings_and_alt():
    page = PageExtraction(
        url="https://example.com",
        final_url="https://example.com",
        title="T",
        meta_description=None,
        h1=[],
        images=[ImageInfo(src="https://example.com/x.png", alt=None)],
    )
    ctx = _ctx([page])
    assert any(i.code == "missing_meta_description" for i in MetaDescriptionAnalyzer().analyze(ctx).issues)
    assert any(i.code == "missing_h1" for i in HeadingsAnalyzer().analyze(ctx).issues)
    alt = ImageAltAnalyzer().analyze(ctx)
    assert any(i.code == "missing_image_alt" for i in alt.issues)
    assert alt.metrics["images_total"] == 1
    assert alt.metrics["pages_missing_alt"] == 1


def test_links_marks_broken_page_not_broken_link():
    page = PageExtraction(
        url="https://example.com/missing",
        final_url="https://example.com/missing",
        is_broken=True,
        error="HTTP 404",
        status_code=404,
    )
    result = LinksAnalyzer().analyze(_ctx([page]))
    assert any(i.code == "broken_page" for i in result.issues)
    assert result.metrics["broken_pages"] == 1


def test_structured_seo_metrics():
    pages = [
        PageExtraction(
            url="https://example.com",
            final_url="https://example.com",
            title="A Complete Title For Metrics Testing Page",
            meta_description="A complete meta description used only for structured metrics aggregation tests.",
            h1=["Hello"],
            h2=["World"],
            images=[ImageInfo(src="https://example.com/a.png", alt="A")],
            internal_links=["https://example.com/about"],
            internal_link_occurrences=2,
            word_count=12,
            has_json_ld=True,
            schema_types=["WebPage"],
            seo_signals={"likely_js_shell": False},
        )
    ]
    metrics = build_structured_seo_metrics(pages)
    assert metrics["coverage"]["titles"] == 1
    assert metrics["totals"]["h1"] == 1
    assert metrics["pages"][0]["internal_link_occurrences"] == 2


def test_large_page():
    page = PageExtraction(
        url="https://example.com",
        final_url="https://example.com",
        title="T",
        h1=["H"],
        content_length=5_000_000,
    )
    result = PageSizeAnalyzer().analyze(_ctx([page]))
    assert any(i.code == "large_page" for i in result.issues)


def test_default_registry_runs():
    registry = build_default_registry()
    assert "title" in registry.list_analyzers()
    results = registry.run_all(
        _ctx(
            [
                PageExtraction(
                    url="https://example.com",
                    final_url="https://example.com",
                    title="Ok Title With Enough Characters Present",
                    meta_description="A sufficiently long meta description used for default registry analyzer smoke tests.",
                    h1=["Hello"],
                )
            ]
        )
    )
    assert len(results) == len(registry.list_analyzers())
