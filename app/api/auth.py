"""Inbound API authentication (SEO_API_KEY + SEO_API_CLIENTS)."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.api.principals import SeoPrincipal, client_map
from app.config.settings import get_settings

# Browser OAuth redirects cannot send Authorization headers.
_PUBLIC_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/google/start",
    "/auth/callback",
    # Production OAuth — privacy policy must be crawlable without API key
    "/legal",
    # Phase 3 — client-facing surfaces (no API key in browser)
    "/share",
    # HTML shell only — JSON /dashboard requires a key when auth is on
    "/dashboard/ui",
    "/alerts/status",
)


def _secure_eq(provided: str, expected: str) -> bool:
    if not provided or not expected or len(provided) != len(expected):
        return False
    return secrets.compare_digest(provided, expected)


def api_key_configured() -> bool:
    """True when any inbound API key (admin or client) is configured."""
    settings = get_settings()
    if (settings.seo_api_key or "").strip():
        return True
    return bool(client_map())


def _extract_api_key(request: Request) -> str | None:
    header_key = request.headers.get("x-api-key")
    if header_key and header_key.strip():
        return header_key.strip()

    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


def resolve_principal(provided: str) -> SeoPrincipal | None:
    """Match provided key to admin SEO_API_KEY or a SEO_API_CLIENTS entry."""
    admin = (get_settings().seo_api_key or "").strip()
    if admin and _secure_eq(provided, admin):
        return SeoPrincipal(role="admin", account_id=None, label="admin")

    for account_id, key in client_map().items():
        if _secure_eq(provided, key):
            return SeoPrincipal(
                role="client",
                account_id=account_id,
                label=account_id,
            )
    return None


def is_public_path(path: str) -> bool:
    path = path.rstrip("/") or "/"
    if path == "/" or path == "/health":
        return True
    for prefix in _PUBLIC_PATH_PREFIXES:
        if prefix == "/health":
            continue
        if path == prefix or path.startswith(prefix + "/"):
            return True
        if path == prefix.rstrip("/"):
            return True
    return False


async def enforce_api_key(request: Request) -> None:
    """Reject protected routes when keys are set and the request lacks a match.

    When neither SEO_API_KEY nor SEO_API_CLIENTS is set, auth is disabled
    (local/dev). Production should always set at least SEO_API_KEY.
    On success, sets request.state.seo_principal.
    """
    request.state.seo_principal = None

    if is_public_path(request.url.path):
        return

    if not api_key_configured():
        return

    provided = _extract_api_key(request)
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing or invalid API key. Pass Authorization: Bearer <key> "
                "or X-API-Key: <key>."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = resolve_principal(provided)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing or invalid API key. Pass Authorization: Bearer <key> "
                "or X-API-Key: <key>."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.seo_principal = principal
