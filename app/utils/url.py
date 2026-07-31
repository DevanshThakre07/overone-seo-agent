"""Pure URL helpers — no business logic."""

from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse, urlunparse


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication: scheme/host lowercased, fragment dropped."""
    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)
    scheme = (parsed.scheme or "http").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def resolve_url(base: str, href: str) -> str | None:
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    absolute = urljoin(base, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    return normalize_url(absolute)


def get_registrable_host(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_same_host(url_a: str, url_b: str) -> bool:
    return get_registrable_host(url_a) == get_registrable_host(url_b)
