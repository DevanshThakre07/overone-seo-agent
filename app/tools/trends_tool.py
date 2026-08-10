"""Hermes-ready tool: score/issue trends from saved audit history."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.repositories.factory import get_audit_repository
from app.services.memory_service import MemoryService


def list_seo_trends(url: str, *, limit: int = 20) -> dict[str, Any]:
    settings = get_settings()
    repo = get_audit_repository(settings)
    return MemoryService(repo).trends(url, limit=limit)
