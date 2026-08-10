"""Persist and query keyword rank snapshots over time."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.dataforseo.serp import normalize_domain
from app.logging import get_logger, log_event
from app.utils.url import normalize_url

logger = get_logger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RankHistoryService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def record_check_result(
        self,
        result: dict[str, Any],
        *,
        seed_url: str | None = None,
        audit_id: str | None = None,
        source: str = "rank_check",
    ) -> dict[str, Any] | None:
        """Persist one check_rank-shaped result when status is ok."""
        if not result or result.get("status") != "ok":
            return None
        rank = result.get("rank") or {}
        keyword = str(result.get("keyword") or "").strip()
        if not keyword:
            return None
        domain = normalize_domain(
            str(rank.get("target") or seed_url or result.get("target") or "")
        )
        if not domain:
            return None
        seed = normalize_url(seed_url or f"https://{domain}/")
        row = {
            "seed_url": seed,
            "target_domain": domain,
            "keyword": keyword,
            "checked_at": _utcnow_iso(),
            "found": bool(rank.get("found")),
            "position": rank.get("position"),
            "rank_absolute": rank.get("rank_absolute"),
            "result_url": rank.get("url"),
            "title": rank.get("title"),
            "device": result.get("device"),
            "provider": result.get("provider") or "dataforseo",
            "audit_id": audit_id,
            "source": source,
            "payload": {
                "message": result.get("message"),
                "top_organic": (result.get("top_organic") or [])[:5],
            },
        }
        saved = self.repository.record(row)
        log_event(
            logger,
            "rank_snapshot_saved",
            keyword=keyword,
            domain=domain,
            found=row["found"],
            position=row["position"],
            source=source,
        )
        return saved

    def record_serp_block(
        self,
        serp_block: dict[str, Any],
        *,
        seed_url: str,
        audit_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Dual-write audit summary.serp checks into rank_snapshots."""
        if not serp_block or serp_block.get("status") != "ok":
            return []
        saved: list[dict[str, Any]] = []
        for check in serp_block.get("checks") or []:
            row = self.record_check_result(
                check,
                seed_url=seed_url or serp_block.get("seed_url"),
                audit_id=audit_id,
                source="audit_serp",
            )
            if row:
                saved.append(row)
        return saved

    def history(
        self,
        *,
        url: str | None = None,
        target: str | None = None,
        keyword: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        seed = normalize_url(url) if url else None
        domain = normalize_domain(target or url or "") if (target or url) else None
        points = self.repository.list_history(
            seed_url=seed,
            target_domain=domain if not seed else None,
            keyword=keyword,
            limit=limit,
        )
        # If filtered by seed only and empty, retry by domain.
        if not points and seed and domain:
            points = self.repository.list_history(
                target_domain=domain,
                keyword=keyword,
                limit=limit,
            )
        series = self._series_by_keyword(points)
        return {
            "status": "ok" if points else "empty",
            "url": seed,
            "target_domain": domain,
            "keyword": (keyword or "").strip().lower() or None,
            "count": len(points),
            "points": points,
            "series": series,
            "message": (
                ""
                if points
                else (
                    "No rank snapshots yet. Run an audit with include_serp=true "
                    "and target_keywords, or GET /rank."
                )
            ),
        }

    def _series_by_keyword(
        self, points: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        # points are newest-first; reverse for charting
        for p in reversed(points):
            kw = p.get("keyword") or ""
            out.setdefault(kw, []).append(
                {
                    "checked_at": p.get("checked_at"),
                    "found": p.get("found"),
                    "position": p.get("position"),
                    "audit_id": p.get("audit_id"),
                    "source": p.get("source"),
                }
            )
        return out
