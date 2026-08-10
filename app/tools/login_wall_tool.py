"""Dry-run login-wall detection — never uses credentials."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.services.crawler_service import CrawlerService


def check_login_wall(url: str) -> dict[str, Any]:
    """Public GET probe + heuristics. Credentials are never attached."""
    settings = get_settings()
    return CrawlerService(settings).probe_login_wall(url)
