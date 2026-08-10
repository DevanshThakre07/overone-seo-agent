"""Fetch and summarize robots.txt for analyzers (read-only GET)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from app.crawler.client import HttpClient


def robots_url_for(seed_url: str) -> str:
    parsed = urlparse(seed_url if "://" in seed_url else f"https://{seed_url}")
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def fetch_robots_snapshot(
    seed_url: str,
    client: HttpClient,
    *,
    user_agent: str = "*",
) -> dict[str, Any]:
    """Return a JSON-safe robots.txt snapshot for scoring and reports."""
    robots_url = robots_url_for(seed_url)
    parsed = urlparse(seed_url if "://" in seed_url else f"https://{seed_url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    fetch = client.get(robots_url)

    if fetch.error:
        return {
            "status": "error",
            "robots_url": robots_url,
            "message": fetch.error,
            "sitemap_refs": [],
            "disallow_all": False,
            "seed_allowed": True,
        }

    if fetch.status_code is None or fetch.status_code >= 400:
        return {
            "status": "missing",
            "robots_url": robots_url,
            "http_status": fetch.status_code,
            "sitemap_refs": [],
            "disallow_all": False,
            "seed_allowed": True,
            "message": f"HTTP {fetch.status_code} for robots.txt",
        }

    text = fetch.text or ""
    sitemap_refs: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            loc = stripped.split(":", 1)[1].strip()
            if loc:
                sitemap_refs.append(loc)

    rp = RobotFileParser()
    rp.set_url(robots_url)
    rp.parse(text.splitlines())
    seed_path = parsed.path or "/"
    seed_check = f"{origin}{seed_path}"
    seed_allowed = rp.can_fetch(user_agent, seed_check)
    # Disallow-all: neither * nor our UA may fetch the site root.
    root = f"{origin}/"
    disallow_all = (not rp.can_fetch("*", root)) and (not rp.can_fetch(user_agent, root))

    return {
        "status": "ok",
        "robots_url": robots_url,
        "http_status": fetch.status_code,
        "byte_length": len(text.encode("utf-8", errors="ignore")),
        "line_count": len(text.splitlines()),
        "sitemap_refs": sitemap_refs,
        "sitemap_ref_count": len(sitemap_refs),
        "disallow_all": disallow_all,
        "seed_allowed": seed_allowed,
        "has_content": bool(text.strip()),
    }
