"""Google Search Console API client (REST, requests-based)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import requests

SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
SEARCH_ANALYTICS_URL = (
    "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
)


class SearchConsoleError(RuntimeError):
    """Raised when a Search Console API call fails."""


class SearchConsoleClient:
    def __init__(self, access_token: str, *, timeout: float = 30.0) -> None:
        self.access_token = access_token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def list_sites(self) -> list[dict[str, Any]]:
        response = requests.get(SITES_URL, headers=self._headers(), timeout=self.timeout)
        if response.status_code >= 400:
            raise SearchConsoleError(
                f"list_sites failed ({response.status_code}): {response.text[:500]}"
            )
        payload = response.json() or {}
        return list(payload.get("siteEntry") or [])

    def search_analytics(
        self,
        site_url: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        dimensions: list[str] | None = None,
        row_limit: int = 25,
        start_row: int = 0,
    ) -> dict[str, Any]:
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=28))
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dimensions or ["query"],
            "rowLimit": row_limit,
            "startRow": start_row,
        }
        encoded_site = quote(site_url, safe="")
        url = SEARCH_ANALYTICS_URL.format(site=encoded_site)
        response = requests.post(
            url, headers=self._headers(), json=body, timeout=self.timeout
        )
        if response.status_code >= 400:
            raise SearchConsoleError(
                f"search_analytics failed ({response.status_code}): {response.text[:500]}"
            )
        return response.json() or {}

    def performance_snapshot(
        self,
        site_url: str,
        *,
        days: int = 28,
        top_n: int = 20,
    ) -> dict[str, Any]:
        """Top queries + pages + opportunity candidates (pos 11–20, high impressions)."""
        end = date.today()
        start = end - timedelta(days=days)

        queries = self.search_analytics(
            site_url,
            start_date=start,
            end_date=end,
            dimensions=["query"],
            row_limit=top_n,
        )
        pages = self.search_analytics(
            site_url,
            start_date=start,
            end_date=end,
            dimensions=["page"],
            row_limit=top_n,
        )
        query_page = self.search_analytics(
            site_url,
            start_date=start,
            end_date=end,
            dimensions=["query", "page"],
            row_limit=100,
        )

        opportunities: list[dict[str, Any]] = []
        for row in query_page.get("rows") or []:
            keys = row.get("keys") or []
            if len(keys) < 2:
                continue
            position = float(row.get("position") or 0)
            impressions = int(row.get("impressions") or 0)
            ctr = float(row.get("ctr") or 0)
            clicks = int(row.get("clicks") or 0)
            query, page = keys[0], keys[1]
            base = {
                "query": query,
                "page": page,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": round(ctr, 4),
                "position": round(position, 2),
            }
            # Page 2 with volume — push into top 10 via title/meta targeting the query.
            if 11.0 <= position <= 20.0 and impressions >= 50:
                opportunities.append(
                    {
                        **base,
                        "kind": "page2",
                        "why": (
                            "Ranking on page 2 with meaningful impressions — "
                            "title/meta rewrite targeting this query is high ROI."
                        ),
                    }
                )
            # Strong position but weak CTR — snippet underperforming.
            elif (
                1.0 <= position <= 10.0
                and impressions >= 50
                and ctr < _ctr_floor_for_position(position)
            ):
                floor = _ctr_floor_for_position(position)
                opportunities.append(
                    {
                        **base,
                        "kind": "low_ctr",
                        "why": (
                            f"Position {position:.1f} with {impressions} impressions but "
                            f"CTR {ctr:.1%} is below a typical ~{floor:.0%} floor — "
                            "improve title/meta to win more clicks for this query."
                        ),
                    }
                )
        opportunities.sort(key=lambda r: (-r["impressions"], r["position"]))

        return {
            "site_url": site_url,
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "top_queries": _rows_as_dicts(queries.get("rows") or [], ["query"]),
            "top_pages": _rows_as_dicts(pages.get("rows") or [], ["page"]),
            "opportunities": opportunities[:top_n],
            "opportunity_count": len(opportunities),
            "status": "ok",
            "source": "google_search_console",
        }


def _ctr_floor_for_position(position: float) -> float:
    """Conservative CTR floors — flag clearly weak snippets, not borderline ones."""
    if position <= 3.0:
        return 0.05
    if position <= 5.0:
        return 0.03
    if position <= 10.0:
        return 0.015
    return 0.0


def _rows_as_dicts(rows: list[dict[str, Any]], dim_names: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        keys = row.get("keys") or []
        item: dict[str, Any] = {
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
            "ctr": round(float(row.get("ctr") or 0), 4),
            "position": round(float(row.get("position") or 0), 2),
        }
        for i, name in enumerate(dim_names):
            item[name] = keys[i] if i < len(keys) else None
        out.append(item)
    return out
