"""PageSpeed Insights HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_pagespeed_service
from app.integrations.google.pagespeed_service import PageSpeedService

router = APIRouter(tags=["pagespeed"])


@router.get("/pagespeed")
def run_pagespeed(
    url: str = Query(..., description="Public page URL to analyze"),
    strategy: str | None = Query(
        None,
        description="Override: mobile | desktop | both (default from config)",
    ),
    service: PageSpeedService = Depends(get_pagespeed_service),
):
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "GOOGLE_PAGESPEED_API_KEY is not set. Create an API key in Google Cloud "
                "Console, enable PageSpeed Insights API, then restart seo-api."
            ),
        )
    if strategy:
        service.settings.pagespeed.strategy = strategy
    result = service.analyze(url)
    # Never leak issue_objects if somehow still present
    result.pop("issue_objects", None)
    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message") or "PageSpeed failed")
    return result


@router.get("/pagespeed/status")
def pagespeed_status(service: PageSpeedService = Depends(get_pagespeed_service)):
    configured = service.is_configured()
    return {
        "configured": configured,
        "enabled": service.settings.pagespeed.enabled,
        "strategy": service.settings.pagespeed.strategy,
        "message": (
            "PageSpeed Insights ready."
            if configured
            else "Set GOOGLE_PAGESPEED_API_KEY to enable Core Web Vitals checks."
        ),
    }
