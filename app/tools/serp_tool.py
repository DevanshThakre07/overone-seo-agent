"""Hermes-ready tools: SERP top results + domain rank check."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.integrations.dataforseo.competitive import CompetitiveSeoService


def check_serp(
    keyword: str,
    *,
    depth: int = 10,
    location_code: int | None = None,
    language_code: str | None = None,
    device: str = "desktop",
) -> dict[str, Any]:
    return CompetitiveSeoService(get_settings()).check_serp(
        keyword,
        depth=depth,
        location_code=location_code,
        language_code=language_code,
        device=device,
    )


def check_rank(
    keyword: str,
    target: str,
    *,
    depth: int = 20,
    location_code: int | None = None,
    language_code: str | None = None,
    device: str = "desktop",
    save: bool = True,
) -> dict[str, Any]:
    result = CompetitiveSeoService(get_settings()).check_rank(
        keyword,
        target,
        depth=depth,
        location_code=location_code,
        language_code=language_code,
        device=device,
    )
    if save and result.get("status") == "ok":
        try:
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
