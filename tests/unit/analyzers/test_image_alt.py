"""alt="" is valid HTML for decorative images and must not be reported."""

from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.analyzers.image_alt_analyzer import ImageAltAnalyzer
from app.config.settings import AnalyzerSettings
from app.extractor.html_extractor import HtmlExtractor
from app.models.crawl import CrawlResult, CrawlStats
from app.models.page import ImageInfo, PageExtraction

SEED = "https://example.com/"


def _page(images: list[ImageInfo]) -> PageExtraction:
    return PageExtraction(
        url=SEED,
        final_url=SEED,
        status_code=200,
        images=images,
    )


def _analyze(images: list[ImageInfo]):
    context = AnalysisContext(
        seed_url=SEED,
        pages=[_page(images)],
        crawl_stats=CrawlStats(seed_url=SEED, pages_crawled=1),
        config=AnalyzerSettings(),
    )
    result = ImageAltAnalyzer().analyze(context)
    return result.metrics, [i.code for i in result.issues]


def _extract(html: str) -> list[ImageInfo]:
    crawl = CrawlResult(
        url=SEED,
        final_url=SEED,
        status_code=200,
        html=html,
    )
    return HtmlExtractor().extract(crawl, SEED).images


class TestAnalyzerDistinguishesAltCases:
    def test_missing_attribute_is_flagged(self):
        metrics, codes = _analyze([ImageInfo(src="/a.png", alt_present=False)])
        assert codes == ["missing_image_alt"]
        assert metrics["missing_alt"] == 1

    def test_explicit_empty_alt_is_not_flagged(self):
        metrics, codes = _analyze(
            [ImageInfo(src="/deco.png", alt="", alt_present=True, decorative=True)]
        )
        assert codes == []
        assert metrics["missing_alt"] == 0
        assert metrics["decorative_images"] == 1

    def test_whitespace_alt_is_a_separate_low_severity_hint(self):
        metrics, codes = _analyze(
            [ImageInfo(src="/x.png", alt="   ", alt_present=True)]
        )
        assert codes == ["whitespace_image_alt"]
        assert metrics["missing_alt"] == 0

    def test_source_elements_are_never_flagged(self):
        metrics, codes = _analyze([ImageInfo(src="/x.webp", is_source=True)])
        assert codes == []
        assert metrics["source_elements_skipped"] == 1

    def test_coverage_ignores_decorative_images(self):
        metrics, _ = _analyze(
            [
                ImageInfo(src="/good.png", alt="A cat", alt_present=True),
                ImageInfo(src="/d1.png", alt="", alt_present=True, decorative=True),
                ImageInfo(src="/d2.png", alt="", alt_present=True, decorative=True),
            ]
        )
        assert metrics["alt_coverage_pct"] == 100.0


class TestExtractorMarksDecorativeImages:
    def test_empty_alt_marked_decorative_missing_alt_is_not(self):
        images = _extract('<img src="/deco.png" alt=""><img src="/bad.png">')
        deco = next(i for i in images if "deco" in i.src)
        bad = next(i for i in images if "bad" in i.src)
        assert deco.alt_present and deco.decorative
        assert not bad.alt_present and not bad.decorative

    def test_aria_and_role_presentation_are_decorative(self):
        images = _extract(
            '<img src="/a.png" role="presentation">'
            '<img src="/b.png" aria-hidden="true">'
        )
        assert all(i.decorative for i in images)

    def test_tracking_pixel_is_decorative(self):
        images = _extract('<img src="/px.gif" width="1" height="1">')
        assert images[0].decorative

    def test_picture_source_is_marked_as_source(self):
        images = _extract(
            "<picture><source srcset='/hero.webp'>"
            "<img src='/hero.jpg' alt='Hero'></picture>"
        )
        source = next(i for i in images if "webp" in i.src)
        assert source.is_source

    def test_image_heavy_decorative_page_reports_no_issues(self):
        html = "".join(f'<img src="/i{n}.png" alt="">' for n in range(60))
        metrics, codes = _analyze(_extract(html))
        assert codes == []
        assert metrics["decorative_images"] == 60
