"""Login-wall dry-run — never attaches credentials."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.logging import get_logger, log_event
from app.tools.login_wall_tool import check_login_wall

router = APIRouter(tags=["crawl-auth"])
logger = get_logger(__name__)


@router.get("/crawl/login-wall")
def login_wall_get(url: str = Query(..., description="URL to probe without credentials")) -> dict:
    log_event(logger, "api_login_wall_probe", url=url)
    try:
        return check_login_wall(url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
