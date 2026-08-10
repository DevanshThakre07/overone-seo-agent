"""Hermes-ready tool: backlinks overview + top referring domains."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.integrations.dataforseo.competitive import CompetitiveSeoService


def check_backlinks(
    target: str,
    *,
    referring_limit: int = 10,
) -> dict[str, Any]:
    return CompetitiveSeoService(get_settings()).check_backlinks(
        target,
        referring_limit=referring_limit,
    )
