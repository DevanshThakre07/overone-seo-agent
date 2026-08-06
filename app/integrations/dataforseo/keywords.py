"""DataForSEO Keywords Data API client (search volume / CPC / competition)."""

from __future__ import annotations

from typing import Any

import requests

from app.config.settings import KeywordSettings

SEARCH_VOLUME_LIVE = (
    "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"
)
USER_DATA = "https://api.dataforseo.com/v3/appendix/user_data"


class DataForSeoError(RuntimeError):
    """Raised when a DataForSEO call fails."""


def parse_search_volume_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize DataForSEO search_volume/live payload into keyword rows."""
    status = payload.get("status_code")
    if status is not None and status != 20000:
        raise DataForSeoError(
            f"DataForSEO error {status}: {payload.get('status_message') or 'unknown'}"
        )

    rows: list[dict[str, Any]] = []
    for task in payload.get("tasks") or []:
        task_status = task.get("status_code")
        if task_status not in (20000, None):
            raise DataForSeoError(
                f"DataForSEO task error {task_status}: "
                f"{task.get('status_message') or 'unknown'}"
            )
        for item in task.get("result") or []:
            if not isinstance(item, dict):
                continue
            keyword = (item.get("keyword") or "").strip()
            if not keyword:
                continue
            rows.append(
                {
                    "keyword": keyword,
                    "search_volume": item.get("search_volume"),
                    "competition": item.get("competition"),
                    "competition_index": item.get("competition_index"),
                    "cpc": item.get("cpc"),
                    "low_top_of_page_bid": item.get("low_top_of_page_bid"),
                    "high_top_of_page_bid": item.get("high_top_of_page_bid"),
                    "location_code": item.get("location_code"),
                    "language_code": item.get("language_code"),
                    "monthly_searches": item.get("monthly_searches") or [],
                }
            )
    return rows


class DataForSeoClient:
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

    def ping(self) -> dict[str, Any]:
        """Cheap auth/balance check via appendix/user_data."""
        try:
            response = requests.get(
                USER_DATA,
                auth=self._auth(),
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataForSeoError(f"DataForSEO user_data request failed: {exc}") from exc
        if response.status_code >= 400:
            raise DataForSeoError(
                f"DataForSEO user_data failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        payload = response.json()
        if payload.get("status_code") != 20000:
            raise DataForSeoError(
                f"DataForSEO error {payload.get('status_code')}: "
                f"{payload.get('status_message')}"
            )
        result = ((payload.get("tasks") or [{}])[0].get("result") or [None])[0] or {}
        money = result.get("money") or {}
        return {
            "status": "ok",
            "provider": "dataforseo",
            "login": result.get("login"),
            "balance": money.get("balance"),
        }

    def search_volume(self, keywords: list[str]) -> list[dict[str, Any]]:
        cleaned = [k.strip() for k in keywords if k and str(k).strip()]
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for kw in cleaned:
            key = kw.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(kw)
        if not unique:
            return []

        limit = max(1, int(self.settings.max_keywords_per_request))
        batch = unique[:limit]
        body = [
            {
                "location_code": self.settings.location_code,
                "language_code": self.settings.language_code,
                "keywords": batch,
            }
        ]
        try:
            response = requests.post(
                SEARCH_VOLUME_LIVE,
                auth=self._auth(),
                json=body,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataForSeoError(f"DataForSEO search_volume failed: {exc}") from exc

        if response.status_code >= 400:
            raise DataForSeoError(
                f"DataForSEO search_volume failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        return parse_search_volume_response(response.json())
