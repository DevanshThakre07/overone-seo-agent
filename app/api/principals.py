"""FP-6 lite — API key → account_id principals (not full IAM)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

from app.config.settings import get_settings


@dataclass(frozen=True, slots=True)
class SeoPrincipal:
    """Authenticated caller after API-key middleware."""

    role: str  # "admin" | "client"
    account_id: str | None  # None = wildcard (admin)
    label: str


def parse_seo_api_clients(raw: str | None) -> dict[str, str]:
    """Parse SEO_API_CLIENTS as JSON object or `id=key,id2=key2` pairs.

    Maps account_id → api_key. Empty / invalid → {}.
    """
    text = (raw or "").strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for account_id, key in data.items():
            aid = str(account_id).strip()
            k = str(key).strip() if key is not None else ""
            if aid and k:
                out[aid] = k
        return out

    out = {}
    for part in text.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        account_id, key = part.split("=", 1)
        aid = account_id.strip()
        k = key.strip()
        if aid and k:
            out[aid] = k
    return out


def client_map() -> dict[str, str]:
    return parse_seo_api_clients(get_settings().seo_api_clients)


def client_isolation_enabled() -> bool:
    return bool(client_map())


def get_principal(request: Request) -> SeoPrincipal | None:
    return getattr(request.state, "seo_principal", None)


def require_account_access(request: Request, account_id: str | None) -> None:
    """403 when a client key targets another customer's account_id.

    No-op when auth is off or the caller is admin. Omitting account_id is
    allowed (no Google tenant data requested).
    """
    principal = get_principal(request)
    if principal is None or principal.role == "admin":
        return

    aid = (account_id or "").strip()
    if not aid:
        return

    if aid != (principal.account_id or ""):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"API key is bound to account_id={principal.account_id!r}; "
                f"cannot access account_id={aid!r}."
            ),
        )


def principal_public_dict(principal: SeoPrincipal | None) -> dict[str, Any]:
    if principal is None:
        return {
            "authenticated": False,
            "role": None,
            "account_id": None,
            "label": None,
            "client_isolation": client_isolation_enabled(),
        }
    return {
        "authenticated": True,
        "role": principal.role,
        "account_id": principal.account_id,
        "label": principal.label,
        "client_isolation": client_isolation_enabled(),
    }
