"""Authenticated crawl helpers — read-only GET, in-memory credentials only."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Crawl must never mutate the target site. Only these methods are allowed.
READ_ONLY_METHODS = frozenset({"GET", "HEAD"})

_LOGIN_PATH_RE = re.compile(
    r"/(login|log-in|signin|sign-in|sign_in|auth|authenticate|session/new|"
    r"account/login|users/sign_in|wp-login\.php)(/|$|\?)",
    re.IGNORECASE,
)


@dataclass
class CrawlAuth:
    """Per-request credentials. Must not be persisted to disk/DB/logs."""

    cookie: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cookie is not None:
            self.cookie = self.cookie.strip() or None
        cleaned: dict[str, str] = {}
        for key, value in (self.headers or {}).items():
            k = str(key).strip()
            v = str(value).strip()
            if not k or not v:
                continue
            # Block attempt to smuggle non-read semantics via odd headers later;
            # credentials themselves are fine on GET.
            if k.lower() in {"cookie"} and self.cookie:
                # Prefer dedicated cookie field; merge if both set.
                self.cookie = f"{self.cookie}; {v}" if self.cookie else v
                continue
            cleaned[k] = v
        self.headers = cleaned

    @property
    def configured(self) -> bool:
        return bool(self.cookie) or bool(self.headers)

    def http_headers(self) -> dict[str, str]:
        """Headers safe to attach to GET/HEAD only."""
        out = dict(self.headers)
        if self.cookie:
            existing = out.get("Cookie") or out.get("cookie")
            if existing:
                out["Cookie"] = f"{existing}; {self.cookie}"
                out.pop("cookie", None)
            else:
                out["Cookie"] = self.cookie
        return out

    def redacted_summary(self) -> dict[str, Any]:
        """Safe for reports/logs — never includes secret values."""
        header_names = sorted({k.lower() for k in self.headers})
        if self.cookie:
            header_names = sorted(set(header_names) | {"cookie"})
        return {
            "credentials_supplied": self.configured,
            "credential_header_names": header_names,
            "cookie_present": bool(self.cookie),
            "credentials_persisted": False,
            "storage": "memory_per_request",
        }


def build_crawl_auth(
    *,
    auth_cookie: str | None = None,
    auth_headers: dict[str, str] | None = None,
) -> CrawlAuth | None:
    auth = CrawlAuth(cookie=auth_cookie, headers=dict(auth_headers or {}))
    return auth if auth.configured else None


def detect_login_wall(
    *,
    url: str,
    final_url: str | None = None,
    status_code: int | None = None,
    html: str | None = None,
) -> dict[str, Any]:
    """Heuristic: does this response look like a login / auth gate?"""
    final = final_url or url
    signals: list[str] = []
    score = 0

    path = urlparse(final).path or "/"
    if _LOGIN_PATH_RE.search(path) or _LOGIN_PATH_RE.search(urlparse(url).path or "/"):
        signals.append("login_path")
        score += 3

    if status_code in {401, 403}:
        signals.append(f"http_{status_code}")
        score += 3

    if html:
        soup = _soup(html)
        password_inputs = soup.find_all("input", attrs={"type": re.compile(r"password", re.I)})
        if password_inputs:
            signals.append("password_input")
            score += 3

        text = soup.get_text(" ", strip=True).lower()[:4000]
        title = (soup.title.get_text(strip=True) if soup.title else "").lower()
        for phrase in (
            "sign in",
            "log in",
            "login",
            "password",
            "forgot password",
            "authenticate",
            "enter your credentials",
        ):
            if phrase in title or phrase in text[:800]:
                signals.append(f"text:{phrase.replace(' ', '_')}")
                score += 1
                break

        # Form posting to login-ish action
        for form in soup.find_all("form"):
            action = str(form.get("action") or "").lower()
            if _LOGIN_PATH_RE.search(action) or "login" in action or "signin" in action:
                signals.append("login_form_action")
                score += 2
                break

    # Deduplicate signals preserving order
    seen: set[str] = set()
    uniq_signals: list[str] = []
    for s in signals:
        if s not in seen:
            seen.add(s)
            uniq_signals.append(s)

    requires_login = score >= 3
    return {
        "requires_login": requires_login,
        "confidence": "high" if score >= 5 else ("medium" if score >= 3 else "low"),
        "score": score,
        "signals": uniq_signals,
        "checked_url": url,
        "final_url": final,
        "status_code": status_code,
        "message": (
            "This site appears to require login (login wall detected). "
            "To audit authenticated pages, supply auth_cookie and/or auth_headers "
            "and set use_authenticated_crawl=true (conscious opt-in). "
            "Credentials are used in-memory only on GET/HEAD — never persisted."
            if requires_login
            else "No strong login wall detected on the public fetch of this URL."
        ),
        "read_only": True,
        "methods_allowed": sorted(READ_ONLY_METHODS),
    }


def auth_policy_block(
    *,
    auth: CrawlAuth | None,
    use_authenticated_crawl: bool,
    login_wall: dict[str, Any] | None,
    credentials_used: bool,
) -> dict[str, Any]:
    """Summary block safe for audit.summary / API responses."""
    supplied = bool(auth and auth.configured)
    ignored = supplied and not use_authenticated_crawl
    mode = "none"
    if credentials_used:
        mode = "authenticated"
    elif login_wall is not None and not credentials_used:
        mode = "detect_only"

    message_parts: list[str] = []
    if login_wall and login_wall.get("requires_login"):
        message_parts.append(login_wall.get("message") or "Login wall detected.")
    if ignored:
        message_parts.append(
            "Credentials were supplied but NOT used — set use_authenticated_crawl=true "
            "to opt in to authenticated GET crawl."
        )
    if credentials_used:
        message_parts.append(
            "Authenticated crawl active: GET/HEAD only, credentials held in memory "
            "for this request and not written to disk, DB, or logs."
        )
    if use_authenticated_crawl and not supplied:
        message_parts.append(
            "use_authenticated_crawl=true but no auth_cookie/auth_headers were provided."
        )

    block: dict[str, Any] = {
        "mode": mode,
        "read_only": True,
        "methods_allowed": sorted(READ_ONLY_METHODS),
        "use_authenticated_crawl": use_authenticated_crawl,
        "credentials_supplied": supplied,
        "credentials_used": credentials_used,
        "credentials_persisted": False,
        "storage": "memory_per_request",
        "login_wall": login_wall,
        "message": " ".join(message_parts) if message_parts else None,
    }
    if auth:
        block.update(auth.redacted_summary())
        block["credentials_used"] = credentials_used
    return block


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")
