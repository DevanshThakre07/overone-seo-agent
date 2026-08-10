"""Hermes/API tool: list historical rank snapshots."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.repositories.factory import get_rank_history_repository
from app.services.rank_history_service import RankHistoryService


def list_rank_history(
    url: str | None = None,
    *,
    target: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if not (url or target):
        return {
            "status": "error",
            "message": "url or target is required",
        }
    return RankHistoryService(get_rank_history_repository(get_settings())).history(
        url=url,
        target=target,
        keyword=keyword,
        limit=limit,
    )
