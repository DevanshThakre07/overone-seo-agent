from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.schemas import OptimizeRequest
from app.logging import get_logger, log_event
from app.tools.keyword_plan_tool import keyword_plan

router = APIRouter(tags=["keyword-plan"])
logger = get_logger(__name__)


@router.post("/keyword-plan")
def create_keyword_plan(payload: OptimizeRequest) -> dict[str, Any]:
    """Live-page keyword placement plan (not SERP rank positions)."""
    log_event(logger, "api_keyword_plan_requested", url=str(payload.url))
    try:
        result = keyword_plan(
            str(payload.url),
            target_keywords=payload.target_keywords or None,
            auth_cookie=payload.auth_cookie,
            auth_headers=payload.auth_headers or None,
            use_authenticated_crawl=payload.use_authenticated_crawl,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message") or "Keyword plan failed")
    return result
