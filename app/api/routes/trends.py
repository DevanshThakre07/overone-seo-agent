"""Score / issue trends from saved audit history."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config.settings import get_settings
from app.repositories.factory import get_audit_repository
from app.services.memory_service import MemoryService

router = APIRouter(tags=["trends"])


@router.get("/trends")
def get_trends(
    url: str = Query(..., description="Site URL to chart"),
    limit: int = Query(20, ge=1, le=100),
):
    if not url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    settings = get_settings()
    repo = get_audit_repository(settings)
    return MemoryService(repo).trends(url, limit=limit)
