from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import OptimizeRequest
from app.logging import get_logger, log_event
from app.models.optimization import OptimizationResult
from app.tools.optimize_tool import optimize_page

router = APIRouter(tags=["optimize"])
logger = get_logger(__name__)


@router.post("/optimize", response_model=OptimizationResult)
def optimize(payload: OptimizeRequest) -> OptimizationResult:
    log_event(logger, "api_optimize_requested", url=str(payload.url))
    try:
        result = optimize_page(
            str(payload.url),
            target_keywords=payload.target_keywords or None,
            auth_cookie=payload.auth_cookie,
            auth_headers=payload.auth_headers or None,
            use_authenticated_crawl=payload.use_authenticated_crawl,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.status == "error":
        raise HTTPException(status_code=400, detail=result.message)
    return result
