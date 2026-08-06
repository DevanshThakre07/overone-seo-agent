"""Defense-in-depth: verify returned data belongs to the URL that was requested."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.utils.url import normalize_url


def _host_and_path(url: str) -> tuple[str, str]:
    parsed = urlparse(normalize_url(url))
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or "/"
    return host, path.rstrip("/") or "/"


def check_url_integrity(
    requested_url: str,
    observed_urls: list[str],
    *,
    redirect_chains: list[list[str]] | None = None,
) -> dict[str, Any]:
    """Confirm at least one fetched page corresponds to the requested URL.

    Redirects are allowed: a redirect chain containing the requested URL, or a
    same-host result, counts as a match. Anything else means the pipeline may be
    returning data for a different page and must say so loudly.
    """
    req_host, req_path = _host_and_path(requested_url)
    chain_urls = {u for chain in (redirect_chains or []) for u in chain}

    exact_match = False
    host_match = False
    for url in observed_urls:
        host, path = _host_and_path(url)
        if host == req_host:
            host_match = True
            if path == req_path:
                exact_match = True
                break

    if not exact_match:
        for url in chain_urls:
            host, path = _host_and_path(url)
            if host == req_host and path == req_path:
                exact_match = True
                break

    ok = exact_match or host_match
    result: dict[str, Any] = {
        "ok": ok,
        "requested_url": requested_url,
        "observed_urls": observed_urls[:10],
        "exact_match": exact_match,
        "same_host": host_match,
        "redirect_followed": bool(chain_urls) and not exact_match,
        "warning": None,
    }
    if not ok:
        result["warning"] = (
            f"URL INTEGRITY FAILURE: results were requested for {requested_url} "
            f"but the fetched page(s) were {observed_urls[:5]}. "
            "Do not trust this data — it may belong to a different site/page."
        )
    elif not exact_match:
        result["warning"] = (
            f"URL was redirected: requested {requested_url}, analyzed "
            f"{observed_urls[:3]} (same host). Findings apply to the redirect target."
        )
    return result
