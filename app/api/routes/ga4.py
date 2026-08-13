"""GA4 Admin + Data API routes (reuse Connect Google account_id)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import get_ga4_service
from app.api.principals import require_account_access
from app.integrations.google.analytics_admin import AnalyticsAdminError
from app.integrations.google.analytics_data import AnalyticsDataError
from app.integrations.google.ga4_service import Ga4Service
from app.integrations.google.oauth import GoogleOAuthError

router = APIRouter(tags=["google-analytics"])


class Ga4PreferenceBody(BaseModel):
    account_id: str = Field(..., description="Same account_id used for Connect Google")
    property_id: str | None = Field(
        None,
        description=(
            "GA4 property id from /ga4/properties (e.g. 533500924). "
            "Omit or null to clear the saved preference."
        ),
    )


@router.get("/ga4/status")
def ga4_status(
    request: Request,
    account_id: str = Query("default"),
    ga4: Ga4Service = Depends(get_ga4_service),
):
    aid = account_id.strip() or "default"
    require_account_access(request, aid)
    return ga4.status(aid)


@router.get("/ga4/properties")
def ga4_properties(
    request: Request,
    account_id: str = Query(..., description="Same account_id used for Connect Google"),
    ga4: Ga4Service = Depends(get_ga4_service),
):
    aid = account_id.strip()
    require_account_access(request, aid)
    try:
        return ga4.list_properties(aid)
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AnalyticsAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/ga4/preference")
def ga4_get_preference(
    request: Request,
    account_id: str = Query(..., description="Connect Google account_id"),
    ga4: Ga4Service = Depends(get_ga4_service),
):
    aid = account_id.strip()
    require_account_access(request, aid)
    preferred = ga4.get_preferred_property_id(aid)
    return {
        "account_id": aid,
        "preferred_ga4_property_id": preferred,
        "status": "ok" if preferred else "none",
        "message": (
            None
            if preferred
            else "No preferred property saved. PUT /ga4/preference to set one."
        ),
    }


@router.put("/ga4/preference")
def ga4_set_preference(
    request: Request,
    body: Ga4PreferenceBody,
    ga4: Ga4Service = Depends(get_ga4_service),
):
    aid = body.account_id.strip()
    require_account_access(request, aid)
    try:
        return ga4.set_preferred_property_id(aid, body.property_id)
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnalyticsAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/ga4/report")
def ga4_report(
    request: Request,
    account_id: str = Query(...),
    property_id: str | None = Query(
        None,
        description=(
            "GA4 property id from /ga4/properties. "
            "Optional if a preferred property was saved via PUT /ga4/preference."
        ),
    ),
    days: int = Query(28, ge=1, le=90),
    top_n: int = Query(20, ge=1, le=50),
    ga4: Ga4Service = Depends(get_ga4_service),
):
    aid = account_id.strip()
    require_account_access(request, aid)
    try:
        resolved = ga4.resolve_property_id(aid, property_id)
        if not resolved:
            raise ValueError(
                "property_id required (or save a preference with PUT /ga4/preference)"
            )
        return ga4.report(
            aid,
            resolved,
            days=days,
            top_n=top_n,
        )
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AnalyticsDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
