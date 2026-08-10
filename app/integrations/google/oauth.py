"""Google OAuth helpers for Search Console (web application flow).

Product owner keeps one OAuth client. Each customer connects their own Google
account via /auth/google/start → Google consent → /auth/callback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests

from app.config.settings import GoogleSearchConsoleSettings, PROJECT_ROOT

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthError(RuntimeError):
    """Raised when OAuth configuration or token exchange fails."""


@dataclass
class OAuthCredentials:
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_in: int | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    id_token: str | None = None
    email: str | None = None


def _resolve_secrets_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def load_oauth_credentials(settings: GoogleSearchConsoleSettings) -> OAuthCredentials:
    """Load client_id/secret from env overrides or the downloaded client JSON."""
    client_id = settings.client_id
    client_secret = settings.client_secret

    secrets_path = _resolve_secrets_path(settings.client_secrets_file)
    if secrets_path.is_file():
        raw = json.loads(secrets_path.read_text(encoding="utf-8"))
        block = raw.get("web") or raw.get("installed") or {}
        client_id = client_id or block.get("client_id")
        client_secret = client_secret or block.get("client_secret")

    if not client_id or not client_secret:
        raise GoogleOAuthError(
            "Google OAuth is not configured. Place the client secret JSON at "
            f"{settings.client_secrets_file} or set GSC_CLIENT_ID / GSC_CLIENT_SECRET."
        )

    return OAuthCredentials(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=settings.redirect_uri,
        scopes=list(settings.scopes),
    )


def build_authorization_url(
    credentials: OAuthCredentials,
    *,
    state: str,
    access_type: str = "offline",
    prompt: str = "select_account consent",
    scopes: list[str] | None = None,
) -> str:
    """Build the Google consent URL.

    Uses %20 encoding (not '+') and puts prompt early — avoids Google 400
    invalid_request when the Location URL gets mangled/truncated.
    prompt includes select_account + consent so the user can pick the
    test Gmail and re-grant Analytics.
    """
    scope_list = list(scopes) if scopes is not None else list(credentials.scopes)
    params = {
        "client_id": credentials.client_id,
        "redirect_uri": credentials.redirect_uri,
        "response_type": "code",
        "access_type": access_type,
        "prompt": prompt,
        "include_granted_scopes": "true",
        "scope": " ".join(scope_list),
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params, quote_via=quote)}"


def exchange_code_for_tokens(
    credentials: OAuthCredentials,
    code: str,
    *,
    timeout: float = 30.0,
) -> TokenBundle:
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "redirect_uri": credentials.redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise GoogleOAuthError(
            f"Token exchange failed ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    access = payload.get("access_token")
    if not access:
        raise GoogleOAuthError("Token exchange returned no access_token")

    email = _fetch_email(access, timeout=timeout)
    return TokenBundle(
        access_token=access,
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in"),
        token_type=payload.get("token_type") or "Bearer",
        scope=payload.get("scope"),
        id_token=payload.get("id_token"),
        email=email,
    )


def refresh_access_token(
    credentials: OAuthCredentials,
    refresh_token: str,
    *,
    timeout: float = 30.0,
) -> TokenBundle:
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise GoogleOAuthError(
            f"Token refresh failed ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    access = payload.get("access_token")
    if not access:
        raise GoogleOAuthError("Token refresh returned no access_token")
    return TokenBundle(
        access_token=access,
        refresh_token=refresh_token,
        expires_in=payload.get("expires_in"),
        token_type=payload.get("token_type") or "Bearer",
        scope=payload.get("scope"),
    )


def _fetch_email(access_token: str, *, timeout: float = 15.0) -> str | None:
    try:
        response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )
        if response.status_code >= 400:
            return None
        data: dict[str, Any] = response.json()
        return data.get("email")
    except requests.RequestException:
        return None
