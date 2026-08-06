"""Hermes-ready tool: research keywords via DataForSEO (Keywords Data + Labs)."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.integrations.dataforseo.service import KeywordResearchService
from app.optimizer.keyword_research import normalize_caller_keywords


def research_keywords_tool(
    keywords: list[str] | str,
    *,
    location_code: int | None = None,
    language_code: str | None = None,
    include_difficulty: bool = True,
    include_related: bool | None = None,
    related_depth: int | None = None,
    related_limit: int | None = None,
) -> dict[str, Any]:
    """Look up volume/CPC plus Labs difficulty and related ideas."""
    if isinstance(keywords, str):
        seeds = [part.strip() for part in keywords.split(",") if part.strip()]
    else:
        seeds = [str(k).strip() for k in keywords if str(k).strip()]

    settings = get_settings()
    previous_loc = settings.keywords.location_code
    previous_lang = settings.keywords.language_code
    try:
        if location_code is not None:
            settings.keywords.location_code = location_code
        if language_code is not None:
            settings.keywords.language_code = language_code
        return KeywordResearchService(settings).research(
            seeds,
            include_difficulty=include_difficulty,
            include_related=include_related,
            related_depth=related_depth,
            related_limit=related_limit,
        )
    finally:
        settings.keywords.location_code = previous_loc
        settings.keywords.language_code = previous_lang


def keyword_difficulty_tool(keywords: list[str] | str) -> dict[str, Any]:
    if isinstance(keywords, str):
        seeds = [part.strip() for part in keywords.split(",") if part.strip()]
    else:
        seeds = [str(k).strip() for k in keywords if str(k).strip()]
    return KeywordResearchService(get_settings()).difficulty(seeds)


def related_keywords_tool(
    keyword: str,
    *,
    depth: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    return KeywordResearchService(get_settings()).related(
        keyword, depth=depth, limit=limit
    )


def keyword_research_status() -> dict[str, Any]:
    return KeywordResearchService(get_settings()).status()


def normalize_keywords(keywords: list[str] | None) -> dict[str, Any]:
    """Same helper used by optimize/audit — exposed for tests/CLI."""
    return normalize_caller_keywords(keywords)
