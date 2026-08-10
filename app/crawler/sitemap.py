"""Fetch and parse XML sitemaps (urlset + sitemapindex). Read-only GET."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

from app.crawler.client import HttpClient
from app.utils.url import normalize_url

_MAX_CHILD_SITEMAPS = 5
_MAX_URLS = 500


def discover_sitemap_candidates(seed_url: str, client: HttpClient) -> list[str]:
    """robots.txt Sitemap: lines first, then conventional /sitemap.xml."""
    parsed = urlparse(seed_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates: list[str] = []

    robots = client.get(f"{origin}/robots.txt")
    if not robots.error and robots.status_code and robots.status_code < 400 and robots.text:
        for line in robots.text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("sitemap:"):
                loc = stripped.split(":", 1)[1].strip()
                if loc:
                    candidates.append(loc)

    conventional = f"{origin}/sitemap.xml"
    if conventional not in candidates:
        candidates.append(conventional)
    return candidates


def fetch_sitemap_snapshot(
    seed_url: str,
    client: HttpClient,
    *,
    max_child_sitemaps: int = _MAX_CHILD_SITEMAPS,
    max_urls: int = _MAX_URLS,
) -> dict[str, Any]:
    """Return a JSON-safe snapshot of sitemap discovery + URL sample."""
    candidates = discover_sitemap_candidates(seed_url, client)
    tried: list[dict[str, Any]] = []
    urls: list[str] = []
    source_sitemaps: list[str] = []
    errors: list[str] = []

    for candidate in candidates:
        if len(urls) >= max_urls:
            break
        fetch = client.get(candidate)
        entry: dict[str, Any] = {
            "url": candidate,
            "status_code": fetch.status_code,
            "ok": bool(not fetch.error and fetch.status_code and fetch.status_code < 400),
            "error": fetch.error,
        }
        tried.append(entry)
        if not entry["ok"] or not fetch.text:
            if fetch.status_code == 404:
                errors.append(f"{candidate}: HTTP 404")
            elif fetch.error:
                errors.append(f"{candidate}: {fetch.error}")
            continue

        parsed = _parse_sitemap_xml(fetch.text)
        entry["kind"] = parsed["kind"]
        if parsed["kind"] == "urlset":
            source_sitemaps.append(candidate)
            for u in parsed["urls"]:
                if u not in urls:
                    urls.append(u)
                if len(urls) >= max_urls:
                    break
        elif parsed["kind"] == "sitemapindex":
            source_sitemaps.append(candidate)
            for child in parsed["sitemaps"][:max_child_sitemaps]:
                if len(urls) >= max_urls:
                    break
                child_fetch = client.get(child)
                if child_fetch.error or not child_fetch.status_code or child_fetch.status_code >= 400:
                    errors.append(f"{child}: fetch failed")
                    continue
                child_parsed = _parse_sitemap_xml(child_fetch.text or "")
                if child_parsed["kind"] != "urlset":
                    continue
                source_sitemaps.append(child)
                for u in child_parsed["urls"]:
                    if u not in urls:
                        urls.append(u)
                    if len(urls) >= max_urls:
                        break
        else:
            errors.append(f"{candidate}: unrecognized sitemap XML")

    found = bool(urls) or any(
        t.get("ok") and t.get("kind") in {"urlset", "sitemapindex"} for t in tried
    )
    # "found" means we successfully parsed at least one sitemap document
    parsed_ok = any(t.get("ok") and t.get("kind") in {"urlset", "sitemapindex"} for t in tried)

    return {
        "status": "ok" if parsed_ok else ("missing" if _all_404(tried) else "error"),
        "candidates": candidates,
        "tried": tried,
        "source_sitemaps": source_sitemaps,
        "url_count": len(urls),
        "urls_sample": urls[:50],
        "urls": urls,
        "errors": errors,
        "truncated": len(urls) >= max_urls,
    }


def coverage_vs_crawl(
    sitemap_urls: list[str],
    crawled_final_urls: list[str],
    *,
    seed_url: str,
) -> dict[str, Any]:
    """How many crawled same-host pages appear in the sitemap."""
    host = urlparse(seed_url).netloc.lower()
    sm_set = {_norm(u) for u in sitemap_urls if urlparse(u).netloc.lower() == host}
    crawled = []
    for u in crawled_final_urls:
        if urlparse(u).netloc.lower() != host:
            continue
        crawled.append(_norm(u))
    crawled_unique = list(dict.fromkeys(crawled))
    missing = [u for u in crawled_unique if u not in sm_set]
    return {
        "crawled_same_host": len(crawled_unique),
        "in_sitemap": len(crawled_unique) - len(missing),
        "missing_from_sitemap": missing[:30],
        "missing_count": len(missing),
        "sitemap_url_count": len(sm_set),
    }


def _all_404(tried: list[dict[str, Any]]) -> bool:
    return bool(tried) and all(t.get("status_code") == 404 for t in tried)


def _norm(url: str) -> str:
    try:
        return normalize_url(url)
    except Exception:
        return url.rstrip("/") or url


def _parse_sitemap_xml(text: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {"kind": "invalid", "urls": [], "sitemaps": []}

    tag = _local(root.tag).lower()
    if tag == "urlset":
        urls: list[str] = []
        for el in root.iter():
            if _local(el.tag).lower() == "loc" and el.text:
                urls.append(el.text.strip())
        return {"kind": "urlset", "urls": urls, "sitemaps": []}
    if tag == "sitemapindex":
        sitemaps: list[str] = []
        for el in root.iter():
            if _local(el.tag).lower() == "loc" and el.text:
                sitemaps.append(el.text.strip())
        return {"kind": "sitemapindex", "urls": [], "sitemaps": sitemaps}
    return {"kind": "unknown", "urls": [], "sitemaps": []}


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag
