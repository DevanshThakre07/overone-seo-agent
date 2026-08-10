"""GA4 service — reuses Connect Google tokens (analytics.readonly)."""

from __future__ import annotations

from typing import Any

from app.config.settings import Settings, get_settings
from app.integrations.google.analytics_admin import (
    AnalyticsAdminClient,
    AnalyticsAdminError,
)
from app.integrations.google.analytics_data import (
    AnalyticsDataClient,
    AnalyticsDataError,
)
from app.integrations.google.oauth import GoogleOAuthError
from app.integrations.google.service import GoogleSearchConsoleService
from app.logging import get_logger, log_event

logger = get_logger(__name__)

ANALYTICS_SCOPE_MARKER = "analytics.readonly"


class Ga4Service:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._google = GoogleSearchConsoleService(self.settings)

    def is_configured(self) -> bool:
        return self._google.is_configured()

    def status(self, account_id: str) -> dict[str, Any]:
        base = self._google.status(account_id)
        preferred = (
            self.get_preferred_property_id(account_id)
            if base.get("connected")
            else None
        )
        return {
            **base,
            "ga4_ready": bool(
                base.get("connected") and base.get("has_analytics_scope")
            ),
            "preferred_ga4_property_id": preferred,
        }

    def list_properties(self, account_id: str) -> dict[str, Any]:
        self._require_analytics(account_id)
        token = self._google.access_token_for(account_id)
        client = AnalyticsAdminClient(token)
        properties = client.list_properties()
        preferred = self.get_preferred_property_id(account_id)
        return {
            "account_id": account_id,
            "properties": properties,
            "count": len(properties),
            "preferred_ga4_property_id": preferred,
            "message": (
                None
                if preferred
                else (
                    "No preferred GA4 property saved. Pick one by name via "
                    "PUT /ga4/preference or the dashboard dropdown, then audits "
                    "with include_ga4=true can omit ga4_property_id."
                )
            ),
        }

    def get_preferred_property_id(self, account_id: str) -> str | None:
        return self._google.store.get_preferred_ga4_property_id(account_id)

    def set_preferred_property_id(
        self, account_id: str, property_id: str | None
    ) -> dict[str, Any]:
        """Save default GA4 property for this Connect Google account_id."""
        self._require_analytics(account_id)
        aid = (account_id or "").strip()
        pid = (property_id or "").strip().removeprefix("properties/") or None
        display = None
        if pid:
            token = self._google.access_token_for(aid)
            props = AnalyticsAdminClient(token).list_properties()
            match = next(
                (p for p in props if str(p.get("property_id")) == pid),
                None,
            )
            if match is None:
                raise ValueError(
                    f"property_id '{pid}' is not in this account's GA4 properties. "
                    "Call GET /ga4/properties and pick a listed id."
                )
            display = match.get("display_name")
        ok = self._google.store.set_preferred_ga4_property_id(aid, pid)
        if not ok:
            raise GoogleOAuthError(
                f"Account '{aid}' is not connected. Call GET /auth/google/start first."
            )
        return {
            "account_id": aid,
            "preferred_ga4_property_id": pid,
            "display_name": display,
            "status": "saved" if pid else "cleared",
            "message": (
                f"Saved preferred GA4 property {pid}"
                + (f" ({display})" if display else "")
                + ". Audits with include_ga4=true can omit ga4_property_id."
                if pid
                else "Cleared preferred GA4 property."
            ),
        }

    def resolve_property_id(
        self, account_id: str | None, property_id: str | None
    ) -> str | None:
        """Explicit property_id wins; else saved preference."""
        explicit = (property_id or "").strip().removeprefix("properties/") or None
        if explicit:
            return explicit
        if not account_id:
            return None
        return self.get_preferred_property_id(account_id.strip())

    def report(
        self,
        account_id: str,
        property_id: str,
        *,
        days: int = 28,
        top_n: int = 20,
    ) -> dict[str, Any]:
        self._require_analytics(account_id)
        pid = (property_id or "").strip()
        if not pid:
            raise ValueError("property_id is required (from GET /ga4/properties)")
        token = self._google.access_token_for(account_id)
        client = AnalyticsDataClient(token)
        snapshot = client.performance_snapshot(
            pid,
            days=max(1, min(int(days or 28), 90)),
            top_n=max(1, min(int(top_n or 20), 50)),
        )
        snapshot["account_id"] = account_id
        return snapshot

    def audit_enrichment(
        self,
        account_id: str | None,
        property_id: str | None,
        *,
        days: int = 28,
    ) -> dict[str, Any]:
        """Attach GA4 snapshot to an audit. Never fails the audit."""
        if not account_id:
            return {
                "status": "skipped",
                "message": (
                    "No gsc_account_id provided. Connect Google, then pass "
                    "include_ga4=true with ga4_property_id (and gsc_account_id)."
                ),
            }
        resolved = self.resolve_property_id(account_id, property_id)
        if not resolved:
            return {
                "status": "skipped",
                "account_id": account_id,
                "message": (
                    "include_ga4 set but no ga4_property_id and no saved preference. "
                    "Pick a property: GET /ga4/properties then PUT /ga4/preference "
                    "(or pass ga4_property_id on the audit)."
                ),
            }
        try:
            status = self.status(account_id)
            if not status.get("connected"):
                return {
                    "status": "not_connected",
                    "account_id": account_id,
                    "message": status.get("message"),
                }
            if not status.get("ga4_ready"):
                return {
                    "status": "missing_scope",
                    "account_id": account_id,
                    "message": (
                        "Connected but missing Analytics scope. Re-open "
                        "/auth/google/start?account_id=... to grant GA4."
                    ),
                }
            snapshot = self.report(
                account_id,
                resolved,
                days=days,
                top_n=15,
            )
            used_saved = not (property_id or "").strip()
            return {
                "status": "ok",
                "account_id": account_id,
                "property_id": resolved,
                "used_saved_preference": used_saved,
                "snapshot": snapshot,
                "has_data": bool(snapshot.get("has_data")),
                "message": snapshot.get("message"),
            }
        except (GoogleOAuthError, AnalyticsAdminError, AnalyticsDataError, ValueError) as exc:
            log_event(
                logger,
                "ga4_enrichment_failed",
                account_id=account_id,
                property_id=property_id,
                error=str(exc),
            )
            return {
                "status": "error",
                "account_id": account_id,
                "property_id": property_id,
                "message": str(exc),
            }

    def _require_analytics(self, account_id: str) -> None:
        status = self._google.status(account_id)
        if not status.get("connected"):
            raise GoogleOAuthError(
                f"Account '{account_id}' is not connected. "
                "Call GET /auth/google/start first."
            )
        if not status.get("has_analytics_scope"):
            raise GoogleOAuthError(
                f"Account '{account_id}' is connected but missing Analytics scope. "
                "Re-open /auth/google/start?account_id=... and approve Analytics access. "
                "Also enable Google Analytics Admin API + Data API in Google Cloud."
            )


def safe_ga4_error(exc: Exception, *, account_id: str | None = None) -> dict[str, Any]:
    log_event(
        logger,
        "ga4_error",
        account_id=account_id,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return {
        "status": "error",
        "account_id": account_id,
        "message": str(exc),
    }


__all__ = [
    "Ga4Service",
    "AnalyticsAdminError",
    "AnalyticsDataError",
    "safe_ga4_error",
    "ANALYTICS_SCOPE_MARKER",
]
