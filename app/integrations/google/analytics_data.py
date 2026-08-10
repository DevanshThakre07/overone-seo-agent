"""Google Analytics Data API (REST) — GA4 runReport."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import requests


class AnalyticsDataError(RuntimeError):
    """Raised when Analytics Data API calls fail."""


class AnalyticsDataClient:
    def __init__(self, access_token: str, *, timeout: float = 45.0) -> None:
        self.access_token = access_token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _property_path(self, property_id: str) -> str:
        pid = (property_id or "").strip()
        if pid.startswith("properties/"):
            return pid
        return f"properties/{pid}"

    def run_report(
        self,
        property_id: str,
        *,
        metrics: list[str],
        dimensions: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=28))
        body: dict[str, Any] = {
            "dateRanges": [
                {"startDate": start.isoformat(), "endDate": end.isoformat()}
            ],
            "metrics": [{"name": m} for m in metrics],
            "limit": str(max(1, min(limit, 100))),
            # Without this, empty properties often return no metricHeaders/rows
            # (totals show as null). Keep empty rows so zeros parse cleanly.
            "keepEmptyRows": True,
        }
        if dimensions:
            body["dimensions"] = [{"name": d} for d in dimensions]
        url = (
            "https://analyticsdata.googleapis.com/v1beta/"
            f"{self._property_path(property_id)}:runReport"
        )
        response = requests.post(
            url, headers=self._headers(), json=body, timeout=self.timeout
        )
        if response.status_code >= 400:
            raise AnalyticsDataError(
                f"runReport failed ({response.status_code}): {response.text[:500]}"
            )
        return response.json() or {}

    def performance_snapshot(
        self,
        property_id: str,
        *,
        days: int = 28,
        top_n: int = 20,
    ) -> dict[str, Any]:
        """Totals (sessions, users, views) + top pages by views."""
        end = date.today()
        start = end - timedelta(days=max(1, min(days, 90)))

        totals_raw = self.run_report(
            property_id,
            metrics=["sessions", "totalUsers", "screenPageViews"],
            start_date=start,
            end_date=end,
            limit=1,
        )
        pages_raw = self.run_report(
            property_id,
            metrics=["screenPageViews", "sessions", "totalUsers"],
            dimensions=["pagePath"],
            start_date=start,
            end_date=end,
            limit=top_n,
        )

        totals = _metric_values(totals_raw)
        sessions = int(totals.get("sessions") or 0)
        users = int(totals.get("totalUsers") or 0)
        views = int(totals.get("screenPageViews") or 0)
        top_pages = []
        for row in pages_raw.get("rows") or []:
            dims = [d.get("value") for d in (row.get("dimensionValues") or [])]
            metrics = _row_metrics(pages_raw, row)
            page_views = int(metrics.get("screenPageViews") or 0)
            if page_views <= 0 and sessions <= 0:
                continue
            top_pages.append(
                {
                    "page_path": dims[0] if dims else None,
                    "screen_page_views": page_views,
                    "sessions": int(metrics.get("sessions") or 0),
                    "total_users": int(metrics.get("totalUsers") or 0),
                }
            )

        return {
            "property_id": property_id.removeprefix("properties/"),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": days,
            "totals": {
                "sessions": sessions,
                "total_users": users,
                "screen_page_views": views,
            },
            "top_pages": top_pages,
            "top_pages_count": len(top_pages),
            "has_data": bool(sessions or users or views or top_pages),
            "message": (
                None
                if (sessions or users or views or top_pages)
                else (
                    "GA4 connected, but this property has 0 sessions/users/views "
                    "in the selected date range. Pick another property_id from "
                    "/ga4/properties (or confirm the site is sending hits to this GA4 property)."
                )
            ),
        }


def _metric_headers(payload: dict[str, Any]) -> list[str]:
    return [h.get("name") for h in (payload.get("metricHeaders") or []) if h.get("name")]


def _row_metrics(payload: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    names = _metric_headers(payload)
    values = [v.get("value") for v in (row.get("metricValues") or [])]
    out: dict[str, Any] = {}
    for name, raw in zip(names, values, strict=False):
        try:
            out[name] = int(float(raw)) if raw is not None else None
        except (TypeError, ValueError):
            out[name] = raw
    return out


def _metric_values(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    if not rows:
        # Some empty properties return totals in metricTotals / empty rows
        return {name: 0 for name in _metric_headers(payload)}
    return _row_metrics(payload, rows[0])
