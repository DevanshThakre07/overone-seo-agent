"""OAuth consent-screen Production readiness (owner-declared + code checklist).

Google Cloud publish / verification is owner-owned. This module surfaces a
machine-readable checklist so status endpoints and Connect Google UX stay honest
about Testing vs Production.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from app.config.settings import GoogleSearchConsoleSettings

PublishingStatus = Literal["testing", "production", "unspecified"]

SENSITIVE_SCOPE_HINTS = {
    "webmasters.readonly": (
        "Search Console (webmasters.readonly) is a sensitive scope. "
        "Production use usually needs Google verification."
    ),
    "analytics.readonly": (
        "Analytics (analytics.readonly) is a sensitive scope. "
        "Production use usually needs Google verification."
    ),
}


def normalize_publishing_status(raw: str | None) -> PublishingStatus:
    value = (raw or "testing").strip().lower()
    if value in ("production", "prod", "published", "live"):
        return "production"
    if value in ("unspecified", "unknown", ""):
        return "unspecified"
    return "testing"


def _is_https_public(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return False
    return bool(host)


def _is_localhost_redirect(uri: str) -> bool:
    parsed = urlparse((uri or "").strip())
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def production_checklist(settings: GoogleSearchConsoleSettings) -> dict[str, Any]:
    """Return owner checklist + what this process believes about publishing."""
    status = normalize_publishing_status(settings.oauth_publishing_status)
    redirect = (settings.redirect_uri or "").strip()
    privacy = (settings.privacy_policy_url or "").strip() or None
    homepage = (settings.homepage_url or "").strip() or None
    scopes = list(settings.scopes or [])

    scope_notes = []
    for scope in scopes:
        for key, note in SENSITIVE_SCOPE_HINTS.items():
            if key in scope:
                scope_notes.append(note)

    steps = [
        {
            "id": "consent_screen_branding",
            "owner": True,
            "done_hint": None,
            "title": "Fill OAuth consent screen",
            "detail": (
                "Google Cloud → APIs & Services → OAuth consent screen: "
                "app name, user support email, developer contact, app logo."
            ),
        },
        {
            "id": "privacy_policy",
            "owner": True,
            "done_hint": bool(privacy and _is_https_public(privacy)),
            "title": "Public privacy policy URL",
            "detail": (
                "Required for Production. Host HTTPS policy (this app serves "
                "GET /legal/privacy when deployed). Set GSC_PRIVACY_POLICY_URL "
                "to the public URL you paste into the consent screen."
            ),
        },
        {
            "id": "homepage",
            "owner": True,
            "done_hint": bool(homepage and _is_https_public(homepage)),
            "title": "App homepage URL",
            "detail": (
                "Consent screen Application home page — usually your product site. "
                "Set GSC_HOMEPAGE_URL."
            ),
        },
        {
            "id": "authorized_domains",
            "owner": True,
            "done_hint": None,
            "title": "Authorized domains",
            "detail": (
                "Add the domain of your homepage / privacy policy / production "
                "redirect (e.g. yourdomain.com) under Authorized domains."
            ),
        },
        {
            "id": "redirect_uris",
            "owner": True,
            "done_hint": bool(redirect)
            and (not _is_localhost_redirect(redirect) or status == "testing"),
            "title": "Production redirect URI",
            "detail": (
                f"Current GSC_REDIRECT_URI={redirect or '(unset)'}. "
                "For live customers add https://YOUR_DOMAIN/auth/callback on the "
                "OAuth Web client and set GSC_REDIRECT_URI to the same value. "
                "Keep localhost listed for local/dev."
            ),
        },
        {
            "id": "enable_apis",
            "owner": True,
            "done_hint": None,
            "title": "Enable required APIs",
            "detail": (
                "Search Console API, Google Analytics Admin API, "
                "Google Analytics Data API (and PageSpeed if used)."
            ),
        },
        {
            "id": "publish_production",
            "owner": True,
            "done_hint": status == "production",
            "title": "Publish consent screen to Production",
            "detail": (
                "OAuth consent screen → Publish app. Until then only Test users "
                "can Connect Google. After you publish, set "
                "GSC_OAUTH_PUBLISHING_STATUS=production in .env and restart seo-api."
            ),
        },
        {
            "id": "verification",
            "owner": True,
            "done_hint": None,
            "title": "Complete Google verification (if prompted)",
            "detail": (
                "webmasters.readonly + analytics.readonly usually trigger "
                "verification for broad Production use: justify scopes, demo video, "
                "privacy policy. Unverified Production apps may show a warning or "
                "limit new users — follow Google’s review email."
            ),
        },
        {
            "id": "seo_api_key",
            "owner": True,
            "done_hint": None,
            "title": "Protect public seo-api",
            "detail": (
                "Set SEO_API_KEY before exposing the API on the internet. "
                "OAuth start/callback and /legal/* stay public by design."
            ),
        },
    ]

    customer_access = (
        "any_google_account"
        if status == "production"
        else "test_users_only"
        if status == "testing"
        else "unknown"
    )

    blocking = []
    if status != "production":
        blocking.append(
            "Consent screen still declared as Testing (or unspecified). "
            "Real customers cannot connect until you Publish + set "
            "GSC_OAUTH_PUBLISHING_STATUS=production."
        )
    if status == "production" and _is_localhost_redirect(redirect):
        blocking.append(
            "Publishing status is production but GSC_REDIRECT_URI is still localhost. "
            "Customers need an https://YOUR_DOMAIN/auth/callback redirect."
        )
    if status == "production" and not (privacy and _is_https_public(privacy)):
        blocking.append(
            "Set GSC_PRIVACY_POLICY_URL to your public https privacy page "
            "(must match the URL on the Google consent screen)."
        )

    return {
        "publishing_status": status,
        "customer_access": customer_access,
        "redirect_uri": redirect or None,
        "privacy_policy_url": privacy,
        "homepage_url": homepage,
        "scopes": scopes,
        "sensitive_scope_notes": scope_notes,
        "blocking": blocking,
        "production_ready": status == "production" and not blocking,
        "steps": steps,
        "docs": "docs/GOOGLE_SEARCH_CONSOLE.md#oauth-production-publish-checklist",
        "message": (
            "OAuth Production is owner-owned in Google Cloud. "
            "This checklist tracks what SEO-Agent can verify from env + what you "
            "must finish in Cloud Console."
            if status != "production"
            else (
                "Declared Production. Confirm Google Cloud shows Publishing status "
                "Production and verification is complete/in progress for your scopes."
                if not blocking
                else "Declared Production but env still has gaps — see blocking."
            )
        ),
    }
