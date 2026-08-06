"""Keyword research — real volume/CPC via DataForSEO when configured.

IMPORTANT:
- User-supplied keywords are inputs, not research by themselves.
- Scraped title/H1/brand words are NOT research.
- This module must never invent search volume, difficulty, or related terms.
- When DataForSEO (or another provider) is configured, research_keywords()
  returns real metrics and is_real_research=True.

Env for DataForSEO:
  KEYWORD_API_PROVIDER=dataforseo
  KEYWORD_API_LOGIN=...
  KEYWORD_API_PASSWORD=...
  KEYWORD_LOCATION_CODE=2840   # optional, default US
  KEYWORD_LANGUAGE_CODE=en     # optional
"""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings


KEYWORD_RESEARCH_UNAVAILABLE = {
    "status": "unavailable",
    "provider": None,
    "is_real_research": False,
    "message": (
        "KEYWORD RESEARCH NOT AVAILABLE: no keyword-data API is configured. "
        "SEO-Agent will not invent search volume, difficulty, or long-tail keywords, "
        "and will not treat brand/title/H1 text as research. "
        "Set KEYWORD_API_PROVIDER=dataforseo plus KEYWORD_API_LOGIN / "
        "KEYWORD_API_PASSWORD in SEO-Agent/.env."
    ),
    "required_to_enable": [
        "Set KEYWORD_API_PROVIDER=dataforseo",
        "Set KEYWORD_API_LOGIN and KEYWORD_API_PASSWORD from app.dataforseo.com/api-access",
        "Restart seo-api / Hermes session",
    ],
    "keywords": [],
}


def research_keywords(
    *,
    seed_terms: list[str] | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Return real keyword metrics when a provider is configured."""
    _ = url  # reserved for future seed expansion from page content
    seeds = [k.strip() for k in (seed_terms or []) if k and str(k).strip()]
    settings = get_settings()
    if not (
        settings.keywords.enabled
        and settings.keywords.provider
        and (
            (
                settings.keywords.provider.lower() == "dataforseo"
                and settings.keywords.login
                and settings.keywords.password
            )
            or settings.keywords.api_key
        )
    ):
        out = dict(KEYWORD_RESEARCH_UNAVAILABLE)
        out["seed_keywords"] = seeds
        return out

    from app.integrations.dataforseo.service import KeywordResearchService

    return KeywordResearchService(settings).research(seeds)


def normalize_caller_keywords(keywords: list[str] | None) -> dict[str, Any]:
    """Merge caller-supplied keywords with real research when available."""
    cleaned = [k.strip() for k in (keywords or []) if k and str(k).strip()]
    research = research_keywords(seed_terms=cleaned or None)

    if research.get("is_real_research") and research.get("status") == "ok":
        return {
            "status": "researched",
            "is_real_research": True,
            "provider": research.get("provider"),
            "message": research.get("message"),
            "keywords": cleaned,
            "metrics": research.get("keywords") or [],
            "related": research.get("related") or [],
            "research": research,
        }

    if not cleaned:
        return {
            "status": "not_provided",
            "is_real_research": False,
            "message": (
                "No target_keywords were provided by the caller. "
                + (
                    research.get("message")
                    or "No keyword-research API configured."
                )
            ),
            "keywords": [],
            "research": research,
        }

    # Caller gave keywords but research failed / unavailable — still honest.
    status = "caller_provided_not_researched"
    if research.get("status") == "error":
        status = "caller_provided_research_error"
    return {
        "status": status,
        "is_real_research": False,
        "message": (
            research.get("message")
            or (
                "These keywords were supplied by the caller only. They are NOT "
                "researched (no search volume, difficulty, or related data)."
            )
        ),
        "keywords": cleaned,
        "research": research,
    }
