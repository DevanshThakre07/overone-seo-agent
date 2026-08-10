"""Google Analytics Admin API (REST) — list GA4 properties."""

from __future__ import annotations

from typing import Any

import requests

ACCOUNT_SUMMARIES_URL = (
    "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
)


class AnalyticsAdminError(RuntimeError):
    """Raised when Analytics Admin API calls fail."""


class AnalyticsAdminClient:
    def __init__(self, access_token: str, *, timeout: float = 30.0) -> None:
        self.access_token = access_token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def list_account_summaries(self, *, page_size: int = 200) -> list[dict[str, Any]]:
        """Return raw accountSummaries pages (flattened)."""
        out: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"pageSize": min(max(page_size, 1), 200)}
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(
                ACCOUNT_SUMMARIES_URL,
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise AnalyticsAdminError(
                    f"accountSummaries failed ({response.status_code}): "
                    f"{response.text[:500]}"
                )
            payload = response.json() or {}
            out.extend(payload.get("accountSummaries") or [])
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return out

    def list_properties(self) -> list[dict[str, Any]]:
        """Flatten to property rows for API/Hermes."""
        rows: list[dict[str, Any]] = []
        for account in self.list_account_summaries():
            account_name = account.get("displayName") or ""
            account_id = (account.get("account") or "").removeprefix("accounts/")
            for prop in account.get("propertySummaries") or []:
                property_resource = prop.get("property") or ""
                property_id = property_resource.removeprefix("properties/")
                rows.append(
                    {
                        "property_id": property_id,
                        "property": property_resource,
                        "display_name": prop.get("displayName") or property_id,
                        "account_id": account_id,
                        "account_name": account_name,
                        "property_type": prop.get("propertyType"),
                    }
                )
        return rows
