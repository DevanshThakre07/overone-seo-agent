"""Customer dashboard aggregate API + static UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.api.principals import require_account_access
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"])

_STATIC = Path(__file__).resolve().parents[2] / "static" / "dashboard.html"


@router.get("/dashboard")
def dashboard_json(
    request: Request,
    url: str = Query(..., description="Site URL"),
    trend_limit: int = Query(12, ge=2, le=50),
    gsc_account_id: str | None = Query(
        None, description="Optional connected GSC account_id for live status/sites"
    ),
    ga4_property_id: str | None = Query(
        None, description="Optional GA4 property_id for live traffic snapshot"
    ),
):
    if not url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    require_account_access(request, gsc_account_id)
    return DashboardService().build(
        url,
        trend_limit=trend_limit,
        gsc_account_id=gsc_account_id,
        ga4_property_id=ga4_property_id,
    )


@router.get("/dashboard/ui")
def dashboard_ui():
    if not _STATIC.exists():
        raise HTTPException(status_code=404, detail="dashboard.html missing")
    return FileResponse(
        _STATIC,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )
