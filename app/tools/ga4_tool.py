"""Hermes-ready tools for Google Analytics 4."""

from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.integrations.google.analytics_admin import AnalyticsAdminError
from app.integrations.google.analytics_data import AnalyticsDataError
from app.integrations.google.ga4_service import Ga4Service
from app.integrations.google.oauth import GoogleOAuthError


def _service() -> Ga4Service:
    return Ga4Service(get_settings())


def ga4_status(account_id: str) -> dict[str, Any]:
    account_id = (account_id or "").strip()
    if not account_id:
        return {"status": "error", "message": "account_id is required"}
    try:
        result = _service().status(account_id)
        return {"status": "ok", **result}
    except GoogleOAuthError as exc:
        return {"status": "error", "account_id": account_id, "message": str(exc)}


def ga4_list_properties(account_id: str) -> dict[str, Any]:
    account_id = (account_id or "").strip()
    if not account_id:
        return {"status": "error", "message": "account_id is required"}
    try:
        result = _service().list_properties(account_id)
        return {"status": "ok", **result}
    except (GoogleOAuthError, AnalyticsAdminError) as exc:
        return {"status": "error", "account_id": account_id, "message": str(exc)}


def ga4_set_preference(
    account_id: str, property_id: str | None = None
) -> dict[str, Any]:
    account_id = (account_id or "").strip()
    if not account_id:
        return {"status": "error", "message": "account_id is required"}
    try:
        result = _service().set_preferred_property_id(account_id, property_id)
        return {"status": "ok", **result}
    except (GoogleOAuthError, AnalyticsAdminError, ValueError) as exc:
        return {"status": "error", "account_id": account_id, "message": str(exc)}


def ga4_get_preference(account_id: str) -> dict[str, Any]:
    account_id = (account_id or "").strip()
    if not account_id:
        return {"status": "error", "message": "account_id is required"}
    preferred = _service().get_preferred_property_id(account_id)
    return {
        "status": "ok" if preferred else "none",
        "account_id": account_id,
        "preferred_ga4_property_id": preferred,
    }


def ga4_report(
    account_id: str,
    property_id: str | None = None,
    *,
    days: int = 28,
    top_n: int = 20,
) -> dict[str, Any]:
    account_id = (account_id or "").strip()
    svc = _service()
    resolved = svc.resolve_property_id(account_id, property_id)
    if not account_id:
        return {"status": "error", "message": "account_id is required"}
    if not resolved:
        return {
            "status": "error",
            "account_id": account_id,
            "message": (
                "property_id required (or save a preference with ga4_set_preference)"
            ),
        }
    try:
        snapshot = svc.report(
            account_id,
            resolved,
            days=max(1, min(int(days or 28), 90)),
            top_n=max(1, min(int(top_n or 20), 50)),
        )
        return {"status": "ok", **snapshot}
    except (GoogleOAuthError, AnalyticsDataError, ValueError, TypeError) as exc:
        return {
            "status": "error",
            "account_id": account_id,
            "property_id": resolved,
            "message": str(exc),
        }
