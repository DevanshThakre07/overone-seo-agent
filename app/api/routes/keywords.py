"""Keyword research HTTP routes (DataForSEO Keywords Data + Labs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_keyword_research_service
from app.integrations.dataforseo.service import KeywordResearchService

router = APIRouter(tags=["keywords"])


@router.get("/keywords/status")
def keywords_status(
    service: KeywordResearchService = Depends(get_keyword_research_service),
):
    return service.status()


@router.get("/keywords/research")
def keywords_research(
    keywords: str = Query(
        ...,
        description="Comma-separated keywords to research (e.g. seo audit,core web vitals)",
    ),
    include_difficulty: bool = Query(
        True, description="Attach DataForSEO Labs keyword_difficulty (0–100)"
    ),
    include_related: bool = Query(
        True,
        description="Also fetch related keywords for the first seed (Labs)",
    ),
    related_depth: int | None = Query(
        None, ge=0, le=4, description="Related search depth 0–4 (default from config)"
    ),
    related_limit: int | None = Query(
        None, ge=1, le=100, description="Max related keywords to return"
    ),
    service: KeywordResearchService = Depends(get_keyword_research_service),
):
    seeds = [part.strip() for part in keywords.split(",") if part.strip()]
    if not seeds:
        raise HTTPException(status_code=400, detail="Provide at least one keyword")
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Keyword research is not configured. Set KEYWORD_API_PROVIDER=dataforseo, "
                "KEYWORD_API_LOGIN, and KEYWORD_API_PASSWORD, then restart seo-api."
            ),
        )
    result = service.research(
        seeds,
        include_difficulty=include_difficulty,
        include_related=include_related,
        related_depth=related_depth,
        related_limit=related_limit,
    )
    if result.get("status") == "error":
        raise HTTPException(
            status_code=502, detail=result.get("message") or "Keyword research failed"
        )
    return result


@router.get("/keywords/difficulty")
def keywords_difficulty(
    keywords: str = Query(..., description="Comma-separated keywords"),
    service: KeywordResearchService = Depends(get_keyword_research_service),
):
    seeds = [part.strip() for part in keywords.split(",") if part.strip()]
    if not seeds:
        raise HTTPException(status_code=400, detail="Provide at least one keyword")
    if not service.labs.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DataForSEO Labs is not configured (same login/password as Keywords Data).",
        )
    result = service.difficulty(seeds)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=502, detail=result.get("message") or "Difficulty lookup failed"
        )
    return result


@router.get("/keywords/related")
def keywords_related(
    keyword: str = Query(..., description="Seed keyword for related ideas"),
    depth: int | None = Query(None, ge=0, le=4),
    limit: int | None = Query(None, ge=1, le=100),
    service: KeywordResearchService = Depends(get_keyword_research_service),
):
    if not service.labs.is_configured():
        raise HTTPException(
            status_code=503,
            detail="DataForSEO Labs is not configured (same login/password as Keywords Data).",
        )
    result = service.related(keyword, depth=depth, limit=limit)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=502, detail=result.get("message") or "Related keywords failed"
        )
    return result
