from pathlib import Path

from app.extractor.html_extractor import HtmlExtractor
from app.models.crawl import CrawlResult

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _result(html: str, url: str = "https://example.com/sample") -> CrawlResult:
    return CrawlResult(
        url=url,
        final_url=url,
        status_code=200,
        html=html,
        content_length=len(html.encode()),
    )


def test_extracts_all_phase1_fields():
    html = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    page = HtmlExtractor().extract(_result(html), "https://example.com")

    assert page.title == "Sample SEO Page With Enough Title Length"
    assert page.title_source == "title"
    assert page.meta_description is not None
    assert page.meta_description_source == "description"
    assert page.h1 == ["Welcome to Sample SEO Page"]
    assert "Features" in page.h2
    assert "Details" in page.h3
    assert page.canonical == "https://example.com/sample"
    assert page.robots_meta == "index,follow"
    assert page.lang == "en"
    assert page.has_viewport is True
    assert any(i.src.endswith("hero.jpg") and i.alt == "Hero image" for i in page.images)
    assert any(i.alt is None or i.alt == "" for i in page.images)
    assert any("responsive.webp" in i.src for i in page.images)
    assert "https://example.com/about" in page.internal_links
    assert page.internal_link_occurrences == 2  # /about appears twice
    assert any("external.example" in u for u in page.external_links)
    assert page.has_json_ld is True
    assert "WebPage" in page.schema_types
    assert "Organization" in page.schema_types
    assert page.word_count > 0
    assert page.seo_signals["h1_count"] == 1
    assert page.image_count == len(page.images)


def test_title_and_meta_fallbacks():
    html = """
    <html><head>
      <meta property="og:title" content="OG Fallback Title For Coverage" />
      <meta property="og:description" content="OG fallback description that is long enough for analyzer checks and extraction." />
    </head><body><p>Hello world content</p></body></html>
    """
    page = HtmlExtractor().extract(_result(html), "https://example.com")
    assert page.title == "OG Fallback Title For Coverage"
    assert page.title_source == "og:title"
    assert page.meta_description_source == "og:description"
    assert "title_fallback_og" in page.extraction_warnings


def test_missing_tags():
    html = (FIXTURES / "missing_tags.html").read_text(encoding="utf-8")
    page = HtmlExtractor().extract(_result(html, "https://example.com/missing"), "https://example.com")
    assert page.title is None
    assert page.meta_description is None
    assert page.h1 == []
