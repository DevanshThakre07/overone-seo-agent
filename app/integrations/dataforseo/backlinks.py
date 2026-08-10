"""DataForSEO Backlinks API — summary + top referring domains."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from app.config.settings import KeywordSettings
from app.integrations.dataforseo.keywords import DataForSeoError

BACKLINKS_SUMMARY_LIVE = "https://api.dataforseo.com/v3/backlinks/summary/live"
BACKLINKS_REFERRING_DOMAINS_LIVE = (
    "https://api.dataforseo.com/v3/backlinks/referring_domains/live"
)


def normalize_backlink_target(value: str) -> str:
    """Domain/subdomain without scheme/www; leave full URLs for page targets."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        # Page-level target — keep absolute URL
        return raw
    # Domain / host form
    host = raw.lower().removeprefix("www.")
    if "/" in host:
        parsed = urlparse(f"https://{host}")
        return (parsed.netloc or host).removeprefix("www.")
    return host


def parse_summary_response(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status_code")
    if status is not None and status != 20000:
        raise DataForSeoError(
            f"DataForSEO backlinks summary error {status}: "
            f"{payload.get('status_message') or 'unknown'}"
        )
    task = (payload.get("tasks") or [{}])[0]
    if task.get("status_code") not in (20000, None):
        raise DataForSeoError(
            f"DataForSEO backlinks summary task error {task.get('status_code')}: "
            f"{task.get('status_message') or 'unknown'}"
        )
    result = (task.get("result") or [None])[0] or {}
    return {
        "target": result.get("target"),
        "rank": result.get("rank"),
        "backlinks": result.get("backlinks"),
        "referring_domains": result.get("referring_domains"),
        "referring_main_domains": result.get("referring_main_domains"),
        "referring_pages": result.get("referring_pages"),
        "referring_ips": result.get("referring_ips"),
        "referring_subnets": result.get("referring_subnets"),
        "crawled_pages": result.get("crawled_pages"),
        "info": result.get("info") or {},
        "broken_backlinks": result.get("broken_backlinks"),
        "broken_pages": result.get("broken_pages"),
        "internal_links_count": result.get("internal_links_count"),
        "external_links_count": result.get("external_links_count"),
    }


def parse_referring_domains_response(payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status_code")
    if status is not None and status != 20000:
        raise DataForSeoError(
            f"DataForSEO referring domains error {status}: "
            f"{payload.get('status_message') or 'unknown'}"
        )
    task = (payload.get("tasks") or [{}])[0]
    if task.get("status_code") not in (20000, None):
        raise DataForSeoError(
            f"DataForSEO referring domains task error {task.get('status_code')}: "
            f"{task.get('status_message') or 'unknown'}"
        )
    result = (task.get("result") or [None])[0] or {}
    items_out: list[dict[str, Any]] = []
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        items_out.append(
            {
                "domain": item.get("domain"),
                "rank": item.get("rank"),
                "backlinks": item.get("backlinks"),
                "first_seen": item.get("first_seen"),
                "backlinks_spam_score": item.get("backlinks_spam_score"),
                "referring_pages": item.get("referring_pages"),
            }
        )
    return {
        "target": result.get("target"),
        "total_count": result.get("total_count"),
        "items_count": result.get("items_count"),
        "referring_domains": items_out,
    }


class DataForSeoBacklinksClient:
    def __init__(self, settings: KeywordSettings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(
            self.settings.enabled
            and (self.settings.provider or "").lower() == "dataforseo"
            and self.settings.login
            and self.settings.password
        )

    def _auth(self) -> tuple[str, str]:
        if not self.settings.login or not self.settings.password:
            raise DataForSeoError(
                "KEYWORD_API_LOGIN and KEYWORD_API_PASSWORD are required for DataForSEO."
            )
        return self.settings.login, self.settings.password

    def summary(self, target: str) -> dict[str, Any]:
        tgt = normalize_backlink_target(target)
        if not tgt:
            raise DataForSeoError("target is required")
        body = [{"target": tgt, "include_subdomains": True}]
        try:
            response = requests.post(
                BACKLINKS_SUMMARY_LIVE,
                auth=self._auth(),
                json=body,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataForSeoError(
                f"DataForSEO backlinks summary failed: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise DataForSeoError(
                f"DataForSEO backlinks summary failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        parsed = parse_summary_response(response.json())
        parsed["source"] = "dataforseo_backlinks_summary_live"
        return parsed

    def referring_domains(self, target: str, *, limit: int = 10) -> dict[str, Any]:
        tgt = normalize_backlink_target(target)
        if not tgt:
            raise DataForSeoError("target is required")
        limit_i = max(1, min(int(limit or 10), 100))
        body = [
            {
                "target": tgt,
                "limit": limit_i,
                "order_by": ["rank,desc"],
                "exclude_internal_backlinks": True,
            }
        ]
        try:
            response = requests.post(
                BACKLINKS_REFERRING_DOMAINS_LIVE,
                auth=self._auth(),
                json=body,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataForSeoError(
                f"DataForSEO referring domains failed: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise DataForSeoError(
                f"DataForSEO referring domains failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        parsed = parse_referring_domains_response(response.json())
        parsed["source"] = "dataforseo_backlinks_referring_domains_live"
        parsed["limit"] = limit_i
        return parsed
