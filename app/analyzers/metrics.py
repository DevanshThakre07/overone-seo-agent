"""Aggregate accurate SEO metrics from page extractions + analyzer results."""

from __future__ import annotations

from typing import Any

from app.models.issues import AnalyzerResult
from app.models.page import PageExtraction


def build_structured_seo_metrics(
    pages: list[PageExtraction],
    analyzer_results: list[AnalyzerResult] | None = None,
) -> dict[str, Any]:
    live_pages = [p for p in pages if not p.is_broken]
    broken_pages = [p for p in pages if p.is_broken]

    titles_present = sum(1 for p in live_pages if p.title)
    meta_present = sum(1 for p in live_pages if p.meta_description)
    h1_present = sum(1 for p in live_pages if p.h1)
    canonical_present = sum(1 for p in live_pages if p.canonical)
    schema_present = sum(1 for p in live_pages if p.has_json_ld or p.schema_types)
    js_shell_pages = sum(
        1 for p in live_pages if (p.seo_signals or {}).get("likely_js_shell")
    )
    js_rendered_pages = sum(1 for p in live_pages if p.js_rendered)

    page_summaries = []
    for page in pages:
        page_summaries.append(
            {
                "url": page.url,
                "final_url": page.final_url,
                "status_code": page.status_code,
                "is_broken": page.is_broken,
                "title": page.title,
                "title_source": page.title_source,
                "title_length": len(page.title) if page.title else 0,
                "meta_description": page.meta_description,
                "meta_description_source": page.meta_description_source,
                "meta_description_length": (
                    len(page.meta_description) if page.meta_description else 0
                ),
                "h1": page.h1,
                "h2": page.h2,
                "h3": page.h3,
                "h1_count": len(page.h1),
                "h2_count": len(page.h2),
                "h3_count": len(page.h3),
                "image_count": page.image_count or len(page.images),
                "images_missing_alt": sum(
                    1
                    for img in page.images
                    if img.alt is None or not str(img.alt).strip()
                ),
                "canonical": page.canonical,
                "robots_meta": page.robots_meta,
                "internal_links_unique": len(page.internal_links),
                "external_links_unique": len(page.external_links),
                "internal_link_occurrences": page.internal_link_occurrences,
                "external_link_occurrences": page.external_link_occurrences,
                "word_count": page.word_count,
                "text_length": page.text_length,
                "content_length": page.content_length,
                "has_json_ld": page.has_json_ld,
                "schema_types": page.schema_types,
                "lang": page.lang,
                "has_viewport": page.has_viewport,
                "js_rendered": page.js_rendered,
                "extraction_warnings": page.extraction_warnings,
                "seo_signals": page.seo_signals,
            }
        )

    analyzer_metrics = {
        result.analyzer: result.metrics
        for result in (analyzer_results or [])
        if result.metrics
    }

    return {
        "pages_total": len(pages),
        "pages_live": len(live_pages),
        "pages_broken": len(broken_pages),
        "coverage": {
            "titles": titles_present,
            "meta_descriptions": meta_present,
            "h1": h1_present,
            "canonical": canonical_present,
            "schema": schema_present,
        },
        "totals": {
            "h1": sum(len(p.h1) for p in live_pages),
            "h2": sum(len(p.h2) for p in live_pages),
            "h3": sum(len(p.h3) for p in live_pages),
            "images": sum(p.image_count or len(p.images) for p in live_pages),
            "internal_links_unique": sum(len(p.internal_links) for p in live_pages),
            "external_links_unique": sum(len(p.external_links) for p in live_pages),
            "internal_link_occurrences": sum(
                p.internal_link_occurrences for p in live_pages
            ),
            "external_link_occurrences": sum(
                p.external_link_occurrences for p in live_pages
            ),
            "word_count": sum(p.word_count for p in live_pages),
        },
        "rendering": {
            "js_shell_pages": js_shell_pages,
            "js_rendered_pages": js_rendered_pages,
        },
        "analyzer_metrics": analyzer_metrics,
        "pages": page_summaries,
    }
