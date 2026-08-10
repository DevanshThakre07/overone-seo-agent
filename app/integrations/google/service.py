"""High-level Google Search Console service used by API routes and audits."""

from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlparse

from app.config.settings import Settings, get_settings
from app.integrations.google.oauth import (
    GoogleOAuthError,
    build_authorization_url,
    exchange_code_for_tokens,
    load_oauth_credentials,
    refresh_access_token,
)
from app.integrations.google.oauth_production import production_checklist
from app.integrations.google.search_console import SearchConsoleClient, SearchConsoleError
from app.integrations.google.token_store import GoogleTokenStore
from app.logging import get_logger, log_event

logger = get_logger(__name__)


class GoogleSearchConsoleService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = GoogleTokenStore(self.settings.gsc.token_db_path)

    def is_configured(self) -> bool:
        try:
            load_oauth_credentials(self.settings.gsc)
            return True
        except GoogleOAuthError:
            return False

    def start_connect(
        self,
        account_id: str,
        *,
        include_analytics: bool = True,
    ) -> dict[str, str]:
        """Return the Google consent URL for this customer account_id."""
        credentials = load_oauth_credentials(self.settings.gsc)
        state = secrets.token_urlsafe(24)
        self.store.save_pending_state(state, account_id)
        scopes = list(credentials.scopes)
        if not include_analytics:
            scopes = [s for s in scopes if "analytics.readonly" not in s]
        url = build_authorization_url(credentials, state=state, scopes=scopes)
        log_event(
            logger,
            "gsc_connect_started",
            account_id=account_id,
            include_analytics=include_analytics,
        )
        return {"authorization_url": url, "state": state, "account_id": account_id}

    def complete_connect(self, *, code: str, state: str) -> dict[str, Any]:
        account_id = self.store.consume_pending_state(state)
        if not account_id:
            raise GoogleOAuthError(
                "Invalid or expired OAuth state. Start Connect Google again."
            )
        credentials = load_oauth_credentials(self.settings.gsc)
        tokens = exchange_code_for_tokens(credentials, code)
        if not tokens.refresh_token:
            # Still store access token; warn that reconnect with consent may be needed.
            log_event(
                logger,
                "gsc_missing_refresh_token",
                account_id=account_id,
                message="No refresh_token returned; re-consent may be required later.",
            )
        self.store.upsert_connection(
            account_id=account_id,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            email=tokens.email,
            scopes=tokens.scope,
        )
        log_event(
            logger,
            "gsc_connect_completed",
            account_id=account_id,
            email=tokens.email,
            has_refresh=bool(tokens.refresh_token),
        )
        scopes = tokens.scope or ""
        has_analytics = "analytics.readonly" in scopes
        return {
            "status": "connected",
            "account_id": account_id,
            "email": tokens.email,
            "has_refresh_token": bool(tokens.refresh_token),
            "has_analytics_scope": has_analytics,
            "message": (
                "Google connected (Search Console"
                + (" + Analytics" if has_analytics else "")
                + "). "
                "Use GET /gsc/sites for Search Console, GET /ga4/properties for GA4."
            ),
        }

    def status(self, account_id: str) -> dict[str, Any]:
        configured = self.is_configured()
        publishing = production_checklist(self.settings.gsc)
        pub_fields = {
            "oauth_publishing_status": publishing["publishing_status"],
            "customer_access": publishing["customer_access"],
            "redirect_uri": publishing["redirect_uri"],
            "production_ready": publishing["production_ready"],
        }
        conn = self.store.get_connection(account_id)
        if conn is None:
            testing_note = ""
            if publishing["publishing_status"] == "testing":
                testing_note = (
                    " OAuth consent is still Testing — only Google accounts listed "
                    "as Test users can connect. See GET /auth/google/production."
                )
            return {
                "configured": configured,
                "connected": False,
                "account_id": account_id,
                "email": None,
                **pub_fields,
                "message": (
                    (
                        "Not connected. Open GET /auth/google/start?account_id=... "
                        "to connect this customer's Google account."
                        + testing_note
                    )
                    if configured
                    else "OAuth client not configured yet."
                ),
            }
        scopes = conn.scopes or ""
        message = None
        if "analytics.readonly" not in scopes:
            message = (
                "Connected for Search Console only. Re-open "
                "/auth/google/start?account_id=... to grant Analytics (GA4)."
            )
        elif publishing["publishing_status"] == "testing":
            message = (
                "Connected (Testing mode). Real customers need OAuth Production — "
                "see GET /auth/google/production."
            )
        return {
            "configured": configured,
            "connected": True,
            "account_id": account_id,
            "email": conn.email,
            "has_refresh_token": bool(conn.refresh_token),
            "has_analytics_scope": "analytics.readonly" in scopes,
            "updated_at": conn.updated_at,
            "scopes": conn.scopes,
            **pub_fields,
            "message": message,
        }

    def production_status(self) -> dict[str, Any]:
        """Owner checklist for publishing OAuth consent to Production."""
        configured = self.is_configured()
        checklist = production_checklist(self.settings.gsc)
        return {
            "configured": configured,
            **checklist,
        }

    def disconnect(self, account_id: str) -> dict[str, Any]:
        deleted = self.store.delete_connection(account_id)
        return {
            "status": "disconnected" if deleted else "not_connected",
            "account_id": account_id,
        }

    def list_sites(self, account_id: str) -> dict[str, Any]:
        access = self._fresh_access_token(account_id)
        client = SearchConsoleClient(access)
        sites = client.list_sites()
        return {
            "account_id": account_id,
            "sites": [
                {
                    "site_url": s.get("siteUrl"),
                    "permission_level": s.get("permissionLevel"),
                }
                for s in sites
            ],
            "count": len(sites),
        }

    def performance(
        self,
        account_id: str,
        site_url: str,
        *,
        days: int = 28,
        top_n: int = 20,
    ) -> dict[str, Any]:
        access = self._fresh_access_token(account_id)
        client = SearchConsoleClient(access)
        snapshot = client.performance_snapshot(site_url, days=days, top_n=top_n)
        snapshot["account_id"] = account_id
        return snapshot

    def audit_enrichment(
        self,
        account_id: str | None,
        seed_url: str,
        *,
        days: int = 28,
    ) -> dict[str, Any]:
        """Attach GSC data to an audit when the customer is connected.

        Never fails the audit — returns an unavailable payload instead.
        """
        if not account_id:
            return {
                "status": "skipped",
                "message": (
                    "No gsc_account_id provided. Customers connect Google once, "
                    "then pass their account_id to include Search Console data."
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
            sites = self.list_sites(account_id)
            matched = _match_site(seed_url, sites.get("sites") or [])
            if not matched:
                return {
                    "status": "no_matching_property",
                    "account_id": account_id,
                    "seed_url": seed_url,
                    "available_sites": [s.get("site_url") for s in sites.get("sites") or []],
                    "message": (
                        "Google is connected, but none of the verified Search Console "
                        "properties match this audit URL. Ask the customer to verify "
                        "the site in Search Console, or pass an exact site_url."
                    ),
                }
            snapshot = self.performance(account_id, matched, days=days)
            return {
                "status": "ok",
                "account_id": account_id,
                "matched_site_url": matched,
                "snapshot": snapshot,
            }
        except (GoogleOAuthError, SearchConsoleError) as exc:
            log_event(
                logger,
                "gsc_enrichment_failed",
                account_id=account_id,
                error=str(exc),
            )
            return {
                "status": "error",
                "account_id": account_id,
                "message": str(exc),
            }

    def access_token_for(self, account_id: str) -> str:
        """Public alias for integrations that share the same Google connection."""
        return self._fresh_access_token(account_id)

    def _fresh_access_token(self, account_id: str) -> str:
        conn = self.store.get_connection(account_id)
        if conn is None:
            raise GoogleOAuthError(
                f"Account '{account_id}' is not connected. "
                "Call GET /auth/google/start first."
            )
        still_valid = (
            conn.token_expiry is not None and conn.token_expiry > time.time() + 30
        )
        if still_valid and conn.access_token:
            return conn.access_token
        if not conn.refresh_token:
            raise GoogleOAuthError(
                f"Access token expired for '{account_id}' and no refresh_token is stored. "
                "Reconnect Google (consent screen) to obtain a refresh token."
            )
        credentials = load_oauth_credentials(self.settings.gsc)
        refreshed = refresh_access_token(credentials, conn.refresh_token)
        self.store.upsert_connection(
            account_id=account_id,
            access_token=refreshed.access_token,
            refresh_token=refreshed.refresh_token,
            expires_in=refreshed.expires_in,
            email=conn.email,
            scopes=refreshed.scope or conn.scopes,
        )
        return refreshed.access_token


def _match_site(seed_url: str, sites: list[dict[str, Any]]) -> str | None:
    """Match an audit URL to a Search Console property (domain or URL-prefix)."""
    if not sites:
        return None
    parsed = urlparse(seed_url if "://" in seed_url else f"https://{seed_url}")
    host = (parsed.netloc or "").lower().removeprefix("www.")
    origin = f"{parsed.scheme}://{parsed.netloc}/"
    candidates = [str(s.get("site_url") or "") for s in sites if s.get("site_url")]

    # Exact URL-prefix match first.
    for site in candidates:
        if site.rstrip("/") + "/" == origin or site == seed_url:
            return site
    # Domain property: sc-domain:example.com
    for site in candidates:
        if site.startswith("sc-domain:"):
            domain = site.removeprefix("sc-domain:").lower().removeprefix("www.")
            if host == domain or host.endswith("." + domain):
                return site
    # Prefix property that covers the host.
    for site in candidates:
        if site.startswith("http") and host in site.lower():
            return site
    return None
