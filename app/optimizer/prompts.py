"""Prompt builders for AI SEO optimization. Grounded in extracted page facts only."""

from __future__ import annotations

import json
from typing import Any

from app.models.page import PageExtraction

SYSTEM_PROMPT = """You are an expert SEO content advisor.
You improve on-page SEO using ONLY the extracted page facts provided.
Do not invent crawl facts, products, claims, or links that are not supported by the input.
If information is missing, suggest conservative improvements and note assumptions in notes.
Return ONLY valid JSON matching the requested schema. No markdown fences."""


def build_page_optimization_messages(
    page: PageExtraction,
    *,
    target_keywords: list[str] | None = None,
    related_internal_urls: list[str] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "url": page.final_url,
        "current": {
            "title": page.title,
            "meta_description": page.meta_description,
            "h1": page.h1,
            "h2": page.h2,
            "canonical": page.canonical,
            "robots_meta": page.robots_meta,
            "internal_links": page.internal_links[:30],
            "external_links": page.external_links[:15],
            "images": [
                {"src": img.src, "alt": img.alt} for img in page.images[:20]
            ],
            "has_json_ld": page.has_json_ld,
            "schema_types": page.schema_types,
        },
        "target_keywords": target_keywords or [],
        "candidate_internal_urls": (related_internal_urls or page.internal_links)[:40],
        "output_schema": {
            "improved_title": "string|null (50-60 chars ideal)",
            "improved_meta_description": "string|null (140-160 chars ideal)",
            "improved_h1": "string|null",
            "heading_suggestions": ["string"],
            "keyword_suggestions": ["string"],
            "faq_suggestions": [{"question": "string", "answer": "string"}],
            "schema_suggestion": {"@context": "https://schema.org", "@type": "WebPage"},
            "internal_link_suggestions": [
                {
                    "anchor_text": "string",
                    "target_url": "string from candidate_internal_urls when possible",
                    "rationale": "string",
                }
            ],
            "notes": ["string"],
        },
    }
    user = (
        "Optimize this page for SEO. Use the facts below.\n\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Respond with a single JSON object containing exactly these keys: "
        "improved_title, improved_meta_description, improved_h1, heading_suggestions, "
        "keyword_suggestions, faq_suggestions, schema_suggestion, "
        "internal_link_suggestions, notes."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_optimization_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first fence and optional last fence
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
