"""DataForSEO Google Organic SERP (live/regular) — top results + rank helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from app.config.settings import KeywordSettings
from app.integrations.dataforseo.keywords import DataForSeoError

SERP_LIVE_REGULAR = (
    "https://api.dataforseo.com/v3/serp/google/organic/live/regular"
)


def normalize_domain(value: str) -> str:
    """Strip scheme/www/path → bare host for matching."""
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    host = urlparse(raw).netloc or urlparse(raw).path.split("/")[0]
    return host.removeprefix("www.")


def domain_matches(candidate: str | None, target: str) -> bool:
    cand = normalize_domain(candidate or "")
    tgt = normalize_domain(target)
    if not cand or not tgt:
        return False
    return cand == tgt or cand.endswith("." + tgt) or tgt.endswith("." + cand)


def parse_serp_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize live/regular SERP payload into organic rows + metadata."""
    status = payload.get("status_code")
    if status is not None and status != 20000:
        raise DataForSeoError(
            f"DataForSEO SERP error {status}: "
            f"{payload.get('status_message') or 'unknown'}"
        )

    task = (payload.get("tasks") or [{}])[0]
    task_status = task.get("status_code")
    if task_status not in (20000, None):
        raise DataForSeoError(
            f"DataForSEO SERP task error {task_status}: "
            f"{task.get('status_message') or 'unknown'}"
        )

    result = (task.get("result") or [None])[0] or {}
    items = result.get("items") or []
    organic: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type not in (None, "organic"):
            continue
        if not item.get("url") and not item.get("domain"):
            continue
        organic.append(
            {
                "rank_group": item.get("rank_group"),
                "rank_absolute": item.get("rank_absolute"),
                "domain": item.get("domain"),
                "url": item.get("url"),
                "title": item.get("title"),
                "description": item.get("description"),
            }
        )

    return {
        "keyword": result.get("keyword"),
        "se_domain": result.get("se_domain"),
        "location_code": result.get("location_code"),
        "language_code": result.get("language_code"),
        "device": result.get("device"),
        "item_types": result.get("item_types") or [],
        "items_count": result.get("items_count"),
        "organic": organic,
        "organic_count": len(organic),
        "check_url": result.get("check_url"),
    }


def find_domain_rank(
    organic: list[dict[str, Any]],
    target: str,
) -> dict[str, Any]:
    """Return best organic position for target domain (or not found)."""
    target_host = normalize_domain(target)
    for row in organic:
        if domain_matches(row.get("domain") or row.get("url"), target_host):
            return {
                "found": True,
                "target": target_host,
                "position": row.get("rank_group"),
                "rank_absolute": row.get("rank_absolute"),
                "url": row.get("url"),
                "title": row.get("title"),
                "domain": row.get("domain"),
            }
    return {
        "found": False,
        "target": target_host,
        "position": None,
        "rank_absolute": None,
        "url": None,
        "title": None,
        "domain": None,
        "message": (
            f"Domain '{target_host}' not found in the returned organic results "
            f"(top {len(organic)})."
        ),
    }


class DataForSeoSerpClient:
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

    def organic_live(
        self,
        keyword: str,
        *,
        depth: int = 10,
        location_code: int | None = None,
        language_code: str | None = None,
        device: str = "desktop",
    ) -> dict[str, Any]:
        kw = (keyword or "").strip()
        if not kw:
            raise DataForSeoError("keyword is required")
        depth_i = max(1, min(int(depth or 10), 100))
        body = [
            {
                "keyword": kw,
                "location_code": location_code or self.settings.location_code,
                "language_code": language_code or self.settings.language_code,
                "device": device if device in {"desktop", "mobile"} else "desktop",
                "depth": depth_i,
            }
        ]
        try:
            response = requests.post(
                SERP_LIVE_REGULAR,
                auth=self._auth(),
                json=body,
                timeout=max(self.settings.timeout_seconds, 90.0),
            )
        except requests.RequestException as exc:
            raise DataForSeoError(f"DataForSEO SERP request failed: {exc}") from exc
        if response.status_code >= 400:
            raise DataForSeoError(
                f"DataForSEO SERP failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        parsed = parse_serp_response(response.json())
        parsed["depth"] = depth_i
        parsed["source"] = "dataforseo_serp_google_organic_live_regular"
        return parsed
