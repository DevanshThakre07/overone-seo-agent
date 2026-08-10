"""Competitive SEO service — SERP, rank check, backlinks (opt-in / paid)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.config.settings import Settings, get_settings
from app.integrations.dataforseo.backlinks import (
    DataForSeoBacklinksClient,
    normalize_backlink_target,
)
from app.integrations.dataforseo.keywords import DataForSeoError
from app.integrations.dataforseo.serp import (
    DataForSeoSerpClient,
    find_domain_rank,
    normalize_domain,
)
from app.logging import get_logger, log_event

logger = get_logger(__name__)


class CompetitiveSeoService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.serp = DataForSeoSerpClient(self.settings.keywords)
        self.backlinks = DataForSeoBacklinksClient(self.settings.keywords)

    def is_configured(self) -> bool:
        return self.serp.is_configured()

    def status(self) -> dict[str, Any]:
        configured = self.is_configured()
        return {
            "configured": configured,
            "provider": "dataforseo" if configured else None,
            "location_code": self.settings.keywords.location_code,
            "language_code": self.settings.keywords.language_code,
            "message": (
                "Competitive SEO ready (SERP / rank / backlinks via DataForSEO)."
                if configured
                else (
                    "Set KEYWORD_API_PROVIDER=dataforseo plus KEYWORD_API_LOGIN / "
                    "KEYWORD_API_PASSWORD to enable SERP, rank, and backlinks."
                )
            ),
        }

    def check_serp(
        self,
        keyword: str,
        *,
        depth: int = 10,
        location_code: int | None = None,
        language_code: str | None = None,
        device: str = "desktop",
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "unavailable",
                "is_real_research": False,
                "message": self.status()["message"],
                "organic": [],
            }
        try:
            snap = self.serp.organic_live(
                keyword,
                depth=depth,
                location_code=location_code,
                language_code=language_code,
                device=device,
            )
            return {
                "status": "ok",
                "provider": "dataforseo",
                "is_real_research": True,
                **snap,
                "message": (
                    f"Top {snap.get('organic_count', 0)} organic result(s) for "
                    f"'{snap.get('keyword') or keyword}'."
                ),
            }
        except DataForSeoError as exc:
            log_event(logger, "serp_failed", keyword=keyword, error=str(exc))
            return {
                "status": "error",
                "provider": "dataforseo",
                "is_real_research": False,
                "keyword": keyword,
                "message": str(exc),
                "organic": [],
            }

    def check_rank(
        self,
        keyword: str,
        target: str,
        *,
        depth: int = 20,
        location_code: int | None = None,
        language_code: str | None = None,
        device: str = "desktop",
    ) -> dict[str, Any]:
        serp = self.check_serp(
            keyword,
            depth=depth,
            location_code=location_code,
            language_code=language_code,
            device=device,
        )
        if serp.get("status") != "ok":
            return {
                **serp,
                "target": normalize_domain(target),
                "rank": None,
            }
        rank = find_domain_rank(serp.get("organic") or [], target)
        return {
            "status": "ok",
            "provider": "dataforseo",
            "is_real_research": True,
            "keyword": serp.get("keyword") or keyword,
            "location_code": serp.get("location_code"),
            "language_code": serp.get("language_code"),
            "device": serp.get("device"),
            "depth": serp.get("depth"),
            "source": serp.get("source"),
            "rank": rank,
            "top_organic": (serp.get("organic") or [])[:5],
            "message": (
                f"Rank #{rank['position']} for '{keyword}'"
                if rank.get("found")
                else rank.get("message")
            ),
        }

    def check_backlinks(
        self,
        target: str,
        *,
        referring_limit: int = 10,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "unavailable",
                "is_real_research": False,
                "message": self.status()["message"],
            }
        tgt = normalize_backlink_target(target)
        if not tgt:
            return {
                "status": "error",
                "message": "target is required (domain or URL)",
            }
        try:
            summary = self.backlinks.summary(tgt)
            referring = self.backlinks.referring_domains(
                tgt, limit=referring_limit
            )
            return {
                "status": "ok",
                "provider": "dataforseo",
                "is_real_research": True,
                "target": tgt,
                "summary": summary,
                "top_referring_domains": referring.get("referring_domains") or [],
                "referring_total_count": referring.get("total_count"),
                "sources": [summary.get("source"), referring.get("source")],
                "message": (
                    f"Backlinks overview for {tgt}: "
                    f"{summary.get('backlinks')} links from "
                    f"{summary.get('referring_domains')} domains."
                ),
            }
        except DataForSeoError as exc:
            log_event(logger, "backlinks_failed", target=tgt, error=str(exc))
            return {
                "status": "error",
                "provider": "dataforseo",
                "is_real_research": False,
                "target": tgt,
                "message": str(exc),
            }

    def audit_serp_enrichment(
        self,
        seed_url: str,
        keywords: list[str],
        *,
        max_keywords: int = 3,
        depth: int = 10,
    ) -> dict[str, Any]:
        """Opt-in audit block: SERP + rank for up to max_keywords."""
        cleaned = [k.strip() for k in keywords if k and str(k).strip()][:max_keywords]
        if not cleaned:
            return {
                "status": "skipped",
                "message": (
                    "include_serp=true requires target_keywords "
                    "(comma-separated keywords to check)."
                ),
            }
        if not self.is_configured():
            return {
                "status": "unavailable",
                "message": self.status()["message"],
            }
        host = normalize_domain(seed_url)
        checks: list[dict[str, Any]] = []
        for kw in cleaned:
            checks.append(self.check_rank(kw, host, depth=depth))
        found = sum(1 for c in checks if (c.get("rank") or {}).get("found"))
        return {
            "status": "ok",
            "provider": "dataforseo",
            "seed_url": seed_url,
            "target_domain": host,
            "keyword_count": len(checks),
            "ranked_count": found,
            "checks": checks,
            "message": (
                f"SERP/rank for {len(checks)} keyword(s); "
                f"{found} found in top results for {host}."
            ),
        }

    def audit_backlinks_enrichment(self, seed_url: str) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "unavailable",
                "message": self.status()["message"],
            }
        host = urlparse(
            seed_url if "://" in seed_url else f"https://{seed_url}"
        ).netloc.removeprefix("www.")
        return self.check_backlinks(host, referring_limit=10)
