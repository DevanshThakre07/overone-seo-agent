"""Guardrails for incomplete JS rendering — avoid confident false SEO findings."""

from __future__ import annotations

from app.models.issues import AnalyzerResult, Issue, Severity
from app.models.page import PageExtraction

# Content-presence checks that are unreliable on unrendered JS shells.
_SUPPRESS_WHEN_UNRENDERED = frozenset(
    {
        "missing_h1",
        "multiple_h1",
        "skipped_heading_level",
        "no_internal_links",
        "missing_schema",
        "schema_untyped",
        "missing_image_alt",
        "missing_canonical",
        # S3 graph / schema — unreliable on unrendered shells
        "orphan_page",
        "dead_end_page",
        "few_internal_links",
        "hub_concentration",
        "missing_organization_schema",
        "missing_website_schema",
        "schema_empty_required",
    }
)


def page_rendering_unreliable(page: PageExtraction) -> bool:
    if page.is_broken:
        return False
    if page.js_rendered:
        return False
    signals = page.seo_signals or {}
    if signals.get("likely_js_shell"):
        return True
    # Extremely thin pages with almost no semantic SEO elements.
    if (
        page.word_count < 30
        and not page.h1
        and not page.internal_links
        and not page.images
    ):
        return True
    return False


def apply_rendering_guardrails(
    pages: list[PageExtraction],
    issues: list[Issue],
    analyzer_results: list[AnalyzerResult],
) -> tuple[list[Issue], list[AnalyzerResult], dict]:
    """Suppress false content findings and surface a top-level rendering warning."""
    unreliable = [p for p in pages if page_rendering_unreliable(p)]
    if not unreliable:
        return issues, analyzer_results, {
            "rendering_incomplete": False,
            "unreliable_pages": [],
            "playwright_available": _playwright_available(),
        }

    unreliable_urls = {p.final_url for p in unreliable}
    kept = [
        issue
        for issue in issues
        if not (
            issue.url in unreliable_urls and issue.code in _SUPPRESS_WHEN_UNRENDERED
        )
    ]

    pw_available = _playwright_available()
    pw_errors = []
    for page in unreliable:
        diag = (page.seo_signals or {}).get("render_diagnostics") or {}
        if diag.get("playwright_error"):
            pw_errors.append({"url": page.final_url, "error": diag.get("playwright_error")})
        if diag.get("playwright"):
            pw_errors.append(
                {
                    "url": page.final_url,
                    "stages": (diag.get("playwright") or {}).get("stages"),
                    "error": diag.get("playwright_error"),
                }
            )
    install_hint = (
        "Playwright is installed but rendering still looks incomplete for these pages. "
        "Inspect rendering.page_diagnostics for stage-level failure logs."
        if pw_available
        else (
            "Install JS rendering to fix this: "
            "pip install 'seo-agent[playwright]' && playwright install chromium "
            "(then set SEO_PLAYWRIGHT_ENABLED=true)."
        )
    )
    urls = sorted(unreliable_urls)
    warning = Issue(
        code="rendering_incomplete",
        severity=Severity.CRITICAL,
        message=(
            "CLIENT-RENDERED PAGE WARNING: static HTML was scraped without a usable "
            "rendered DOM. Word counts, headings, links, images, and schema findings "
            f"are unreliable for {len(urls)} page(s). Score is provisional. {install_hint}"
        ),
        url=urls[0],
        details={
            "unreliable_urls": urls,
            "playwright_available": pw_available,
            "playwright_errors": pw_errors[:10],
            "suppressed_issue_codes": sorted(_SUPPRESS_WHEN_UNRENDERED),
            "recommendation": (
                "Re-run the audit after Playwright successfully captures the "
                "rendered DOM (check logs for playwright_stage / playwright_failed)."
            ),
        },
    )
    kept.insert(0, warning)

    # Mirror the warning into analyzer_results for structured consumers.
    analyzer_results = list(analyzer_results)
    analyzer_results.insert(
        0,
        AnalyzerResult(
            analyzer="rendering",
            issues=[warning],
            metrics={
                "rendering_incomplete": True,
                "unreliable_pages": len(urls),
                "playwright_available": pw_available,
            },
        ),
    )

    meta = {
        "rendering_incomplete": True,
        "unreliable_pages": urls,
        "playwright_available": pw_available,
        "warning": warning.message,
    }
    return kept, analyzer_results, meta


def _playwright_available() -> bool:
    try:
        from app.crawler.playwright_client import PlaywrightClient

        return PlaywrightClient.is_available()
    except Exception:  # noqa: BLE001
        return False
