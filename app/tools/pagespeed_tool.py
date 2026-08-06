"""Hermes-ready tool: PageSpeed Insights / Core Web Vitals for a URL."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.integrations.google.pagespeed_service import PageSpeedService


def _serialize_pagespeed(result: dict[str, Any]) -> dict[str, Any]:
    """Drop Issue objects; keep JSON-safe dicts for Hermes / CLI."""
    out = dict(result)
    out.pop("issue_objects", None)
    strategies = []
    for block in out.get("strategies") or []:
        item = dict(block)
        raw_issues = item.get("issues") or []
        item["issues"] = [
            i.model_dump(mode="json") if hasattr(i, "model_dump") else i
            for i in raw_issues
        ]
        strategies.append(item)
    out["strategies"] = strategies
    if out.get("issues") and hasattr(out["issues"][0], "model_dump"):
        out["issues"] = [i.model_dump(mode="json") for i in out["issues"]]
    return out


def check_pagespeed(
    url: str,
    *,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Run PageSpeed Insights for a live URL (mobile/desktop/both).

    Requires GOOGLE_PAGESPEED_API_KEY. Never raises for config miss — returns
    status=skipped so Hermes can report it cleanly.
    """
    settings = get_settings()
    service = PageSpeedService(settings)
    previous = settings.pagespeed.strategy
    try:
        if strategy:
            normalized = strategy.strip().lower()
            if normalized not in {"mobile", "desktop", "both"}:
                return {
                    "status": "error",
                    "url": url,
                    "message": "strategy must be mobile, desktop, or both",
                    "strategies": [],
                    "issues": [],
                }
            settings.pagespeed.strategy = normalized
            service.client.settings = settings.pagespeed
        return _serialize_pagespeed(service.analyze(url))
    finally:
        settings.pagespeed.strategy = previous
        service.client.settings = settings.pagespeed


def pagespeed_status() -> dict[str, Any]:
    """Whether PageSpeed is configured (no network call)."""
    settings = get_settings()
    configured = bool(settings.pagespeed.enabled and settings.pagespeed.api_key)
    return {
        "configured": configured,
        "enabled": settings.pagespeed.enabled,
        "strategy": settings.pagespeed.strategy,
        "message": (
            "PageSpeed Insights ready."
            if configured
            else "Set GOOGLE_PAGESPEED_API_KEY to enable Core Web Vitals checks."
        ),
    }
