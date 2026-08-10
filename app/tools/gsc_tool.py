"""Hermes-ready tools for Google Search Console (sites / performance / status)."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.integrations.google.oauth import GoogleOAuthError
from app.integrations.google.search_console import SearchConsoleError
from app.integrations.google.service import GoogleSearchConsoleService


def _service() -> GoogleSearchConsoleService:
    return GoogleSearchConsoleService(get_settings())


def gsc_status(account_id: str) -> dict[str, Any]:
    """Whether this account_id is connected (no Search Console API call)."""
    account_id = (account_id or "").strip()
    if not account_id:
        return {
            "status": "error",
            "message": "account_id is required",
        }
    try:
        result = _service().status(account_id)
        return {"status": "ok", **result}
    except GoogleOAuthError as exc:
        return {"status": "error", "account_id": account_id, "message": str(exc)}


def gsc_list_sites(account_id: str) -> dict[str, Any]:
    """List verified Search Console properties for a connected account."""
    account_id = (account_id or "").strip()
    if not account_id:
        return {
            "status": "error",
            "message": "account_id is required",
        }
    try:
        result = _service().list_sites(account_id)
        return {"status": "ok", **result}
    except (GoogleOAuthError, SearchConsoleError) as exc:
        return {"status": "error", "account_id": account_id, "message": str(exc)}


def gsc_performance(
    account_id: str,
    site_url: str,
    *,
    days: int = 28,
    top_n: int = 20,
) -> dict[str, Any]:
    """Pull Search Console performance snapshot (queries, pages, opportunities)."""
    account_id = (account_id or "").strip()
    site_url = (site_url or "").strip()
    if not account_id:
        return {"status": "error", "message": "account_id is required"}
    if not site_url:
        return {
            "status": "error",
            "account_id": account_id,
            "message": "site_url is required (e.g. sc-domain:example.com)",
        }
    try:
        days_i = max(1, min(int(days or 28), 90))
        top_n_i = max(1, min(int(top_n or 20), 50))
        snapshot = _service().performance(
            account_id, site_url, days=days_i, top_n=top_n_i
        )
        return {"status": "ok", **snapshot}
    except (GoogleOAuthError, SearchConsoleError, ValueError, TypeError) as exc:
        return {
            "status": "error",
            "account_id": account_id,
            "site_url": site_url,
            "message": str(exc),
        }
