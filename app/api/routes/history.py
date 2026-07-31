from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import CompareRequest
from app.logging import get_logger, log_event
from app.models.diff import AuditDiff
from app.tools.compare_tool import compare_audits
from app.tools.history_tool import HistoryResult, list_history

router = APIRouter(tags=["history"])
logger = get_logger(__name__)


@router.get("/history", response_model=HistoryResult)
def history(
    url: str = Query(..., description="Site URL to list audits for"),
    limit: int = Query(default=20, ge=1, le=100),
) -> HistoryResult:
    log_event(logger, "api_history_requested", url=url, limit=limit)
    try:
        return list_history(url, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/compare", response_model=AuditDiff)
def compare(payload: CompareRequest) -> AuditDiff:
    log_event(logger, "api_compare_requested", url=str(payload.url))
    try:
        return compare_audits(
            str(payload.url),
            max_pages=payload.max_pages,
            save=payload.save,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
