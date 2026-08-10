"""Inbound API authentication (SEO_API_KEY)."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

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
    "/dashboard",
)


def api_key_configured() -> bool:
    key = (get_settings().seo_api_key or "").strip()
    return bool(key)


def _extract_api_key(request: Request) -> str | None:
    header_key = request.headers.get("x-api-key")
    if header_key and header_key.strip():
        return header_key.strip()

    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    return None


def is_public_path(path: str) -> bool:
    path = path.rstrip("/") or "/"
    if path == "/health":
        return True
    for prefix in _PUBLIC_PATH_PREFIXES:
        if prefix == "/health":
            continue
        if path == prefix or path.startswith(prefix + "/"):
            return True
        # /docs and /redoc may be exact or with trailing slash already handled
        if path == prefix.rstrip("/"):
            return True
    return False


async def enforce_api_key(request: Request) -> None:
    """Reject protected routes when SEO_API_KEY is set and the request lacks it.

    When SEO_API_KEY is unset, auth is disabled (local/dev). Production should
    always set the key.
    """
    if is_public_path(request.url.path):
        return

    expected = (get_settings().seo_api_key or "").strip()
    if not expected:
        return

    provided = _extract_api_key(request)
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing or invalid API key. Pass Authorization: Bearer <SEO_API_KEY> "
                "or X-API-Key: <SEO_API_KEY>."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )
