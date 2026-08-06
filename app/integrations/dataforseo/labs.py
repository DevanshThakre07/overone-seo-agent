"""DataForSEO Labs API — keyword difficulty + related keywords."""

from __future__ import annotations

from typing import Any

import requests

from app.config.settings import KeywordSettings
from app.integrations.dataforseo.keywords import DataForSeoError

BULK_DIFFICULTY_LIVE = (
    "https://api.dataforseo.com/v3/dataforseo_labs/google/bulk_keyword_difficulty/live"
)
RELATED_KEYWORDS_LIVE = (
    "https://api.dataforseo.com/v3/dataforseo_labs/google/related_keywords/live"
)


def _assert_ok(payload: dict[str, Any], *, label: str) -> None:
    status = payload.get("status_code")
    if status is not None and status != 20000:
        raise DataForSeoError(
            f"DataForSEO Labs {label} error {status}: "
            f"{payload.get('status_message') or 'unknown'}"
        )
    for task in payload.get("tasks") or []:
        task_status = task.get("status_code")
        if task_status not in (20000, None):
            raise DataForSeoError(
                f"DataForSEO Labs {label} task error {task_status}: "
                f"{task.get('status_message') or 'unknown'}"
            )


def parse_bulk_difficulty_response(payload: dict[str, Any]) -> dict[str, int | None]:
    """Map keyword → keyword_difficulty (0–100)."""
    _assert_ok(payload, label="bulk_keyword_difficulty")
    out: dict[str, int | None] = {}
    for task in payload.get("tasks") or []:
        for block in task.get("result") or []:
            for item in block.get("items") or []:
                if not isinstance(item, dict):
                    continue
                keyword = (item.get("keyword") or "").strip()
                if not keyword:
                    continue
                difficulty = item.get("keyword_difficulty")
                out[keyword.lower()] = (
                    int(difficulty) if difficulty is not None else None
                )
    return out


def parse_related_keywords_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize related_keywords/live items into compact rows."""
    _assert_ok(payload, label="related_keywords")
    rows: list[dict[str, Any]] = []
    for task in payload.get("tasks") or []:
        for block in task.get("result") or []:
            for item in block.get("items") or []:
                if not isinstance(item, dict):
                    continue
                data = item.get("keyword_data") or {}
                info = data.get("keyword_info") or {}
                props = data.get("keyword_properties") or {}
                keyword = (data.get("keyword") or "").strip()
                if not keyword:
                    continue
                rows.append(
                    {
                        "keyword": keyword,
                        "search_volume": info.get("search_volume"),
                        "cpc": info.get("cpc"),
                        "competition": info.get("competition_level")
                        or info.get("competition"),
                        "keyword_difficulty": props.get("keyword_difficulty"),
                        "depth": item.get("depth"),
                        "related_keywords": item.get("related_keywords") or [],
                    }
                )
    return rows


class DataForSeoLabsClient:
    """Labs endpoints share the same login/password as Keywords Data."""

    def __init__(self, settings: KeywordSettings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(
            self.settings.enabled
            and self.settings.labs_enabled
            and (self.settings.provider or "").lower() == "dataforseo"
            and self.settings.login
            and self.settings.password
        )

    def _auth(self) -> tuple[str, str]:
        if not self.settings.login or not self.settings.password:
            raise DataForSeoError(
                "KEYWORD_API_LOGIN and KEYWORD_API_PASSWORD are required for DataForSEO Labs."
            )
        return self.settings.login, self.settings.password

    def bulk_keyword_difficulty(self, keywords: list[str]) -> dict[str, int | None]:
        cleaned = [k.strip() for k in keywords if k and str(k).strip()]
        seen: set[str] = set()
        unique: list[str] = []
        for kw in cleaned:
            key = kw.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(kw)
        if not unique:
            return {}

        limit = max(1, int(self.settings.max_keywords_per_request))
        body = [
            {
                "location_code": self.settings.location_code,
                "language_code": self.settings.language_code,
                "keywords": unique[:limit],
            }
        ]
        try:
            response = requests.post(
                BULK_DIFFICULTY_LIVE,
                auth=self._auth(),
                json=body,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataForSeoError(
                f"DataForSEO Labs bulk_keyword_difficulty failed: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise DataForSeoError(
                f"DataForSEO Labs bulk_keyword_difficulty failed "
                f"({response.status_code}): {response.text[:500]}"
            )
        return parse_bulk_difficulty_response(response.json())

    def related_keywords(
        self,
        keyword: str,
        *,
        depth: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        seed = (keyword or "").strip()
        if not seed:
            return []
        depth_val = (
            self.settings.related_depth if depth is None else int(depth)
        )
        depth_val = max(0, min(4, depth_val))
        limit_val = (
            self.settings.related_limit if limit is None else int(limit)
        )
        limit_val = max(1, min(1000, limit_val))

        body = [
            {
                "keyword": seed,
                "location_code": self.settings.location_code,
                "language_code": self.settings.language_code,
                "depth": depth_val,
                "limit": limit_val,
                "include_seed_keyword": False,
            }
        ]
        try:
            response = requests.post(
                RELATED_KEYWORDS_LIVE,
                auth=self._auth(),
                json=body,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataForSeoError(
                f"DataForSEO Labs related_keywords failed: {exc}"
            ) from exc
        if response.status_code >= 400:
            raise DataForSeoError(
                f"DataForSEO Labs related_keywords failed "
                f"({response.status_code}): {response.text[:500]}"
            )
        return parse_related_keywords_response(response.json())
