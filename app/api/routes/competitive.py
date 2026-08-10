"""Competitive SEO HTTP routes — SERP, rank, backlinks (DataForSEO, opt-in)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_competitive_seo_service
from app.integrations.dataforseo.competitive import CompetitiveSeoService

router = APIRouter(tags=["competitive"])


@router.get("/competitive/status")
def competitive_status(
    service: CompetitiveSeoService = Depends(get_competitive_seo_service),
):
    return service.status()


@router.get("/serp")
def serp_lookup(
    keyword: str = Query(..., description="Search query to fetch organic SERP for"),
    depth: int = Query(10, ge=1, le=100, description="Organic depth (default 10)"),
    device: str = Query("desktop", description="desktop or mobile"),
    location_code: int | None = Query(None),
    language_code: str | None = Query(None),
    service: CompetitiveSeoService = Depends(get_competitive_seo_service),
):
    if not service.is_configured():
        raise HTTPException(status_code=503, detail=service.status()["message"])
    result = service.check_serp(
        keyword,
        depth=depth,
        device=device,
        location_code=location_code,
        language_code=language_code,
    )
    if result.get("status") == "error":
        raise HTTPException(
            status_code=502, detail=result.get("message") or "SERP lookup failed"
        )
    return result


@router.get("/rank")
def rank_check(
    keyword: str = Query(..., description="Keyword to rank-check"),
    target: str = Query(
        ...,
        description="Client domain or URL (e.g. bookasto.com or https://bookasto.com/)",
    ),
    depth: int = Query(20, ge=1, le=100),
    device: str = Query("desktop"),
    location_code: int | None = Query(None),
    language_code: str | None = Query(None),
    save: bool = Query(True, description="Persist snapshot to rank history"),
    service: CompetitiveSeoService = Depends(get_competitive_seo_service),
):
    if not service.is_configured():
        raise HTTPException(status_code=503, detail=service.status()["message"])
    result = service.check_rank(
        keyword,
        target,
        depth=depth,
        device=device,
        location_code=location_code,
        language_code=language_code,
    )
    if result.get("status") == "error":
        raise HTTPException(
            status_code=502, detail=result.get("message") or "Rank check failed"
        )
    if save and result.get("status") == "ok":
        try:
            from app.config.settings import get_settings
            from app.repositories.factory import get_rank_history_repository
            from app.services.rank_history_service import RankHistoryService

            RankHistoryService(get_rank_history_repository(get_settings())).record_check_result(
                result,
                seed_url=target,
                source="rank_check",
            )
        except Exception:  # noqa: BLE001
            pass
    return result


@router.get("/rank/history")
def rank_history(
    url: str | None = Query(None, description="Site URL (preferred)"),
    target: str | None = Query(None, description="Domain if URL omitted"),
    keyword: str | None = Query(None, description="Filter to one keyword"),
    limit: int = Query(50, ge=1, le=200),
):
    if not (url or target):
        raise HTTPException(status_code=400, detail="url or target is required")
    from app.config.settings import get_settings
    from app.repositories.factory import get_rank_history_repository
    from app.services.rank_history_service import RankHistoryService

    return RankHistoryService(get_rank_history_repository(get_settings())).history(
        url=url,
        target=target,
        keyword=keyword,
        limit=limit,
    )


@router.get("/backlinks")
def backlinks_overview(
    target: str = Query(
        ...,
        description="Domain or URL (e.g. bookasto.com)",
    ),
    referring_limit: int = Query(10, ge=1, le=100),
    service: CompetitiveSeoService = Depends(get_competitive_seo_service),
):
    if not service.is_configured():
        raise HTTPException(status_code=503, detail=service.status()["message"])
    result = service.check_backlinks(target, referring_limit=referring_limit)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=502, detail=result.get("message") or "Backlinks failed"
        )
    return result
