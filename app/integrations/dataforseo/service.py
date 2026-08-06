"""Keyword research service — DataForSEO Keywords Data + Labs."""

from __future__ import annotations

from typing import Any

from app.config.settings import Settings, get_settings
from app.integrations.dataforseo.keywords import DataForSeoClient, DataForSeoError
from app.integrations.dataforseo.labs import DataForSeoLabsClient
from app.logging import get_logger, log_event

logger = get_logger(__name__)


class KeywordResearchService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = DataForSeoClient(self.settings.keywords)
        self.labs = DataForSeoLabsClient(self.settings.keywords)

    def is_configured(self) -> bool:
        provider = (self.settings.keywords.provider or "").lower()
        if provider == "dataforseo":
            return self.client.is_configured()
        return False

    def status(self) -> dict[str, Any]:
        provider = (self.settings.keywords.provider or "").lower() or None
        configured = self.is_configured()
        labs_ready = self.labs.is_configured()
        return {
            "configured": configured,
            "enabled": self.settings.keywords.enabled,
            "provider": provider,
            "location_code": self.settings.keywords.location_code,
            "language_code": self.settings.keywords.language_code,
            "labs": {
                "enabled": self.settings.keywords.labs_enabled,
                "configured": labs_ready,
                "related_depth": self.settings.keywords.related_depth,
                "related_limit": self.settings.keywords.related_limit,
                "include_related_in_research": (
                    self.settings.keywords.include_related_in_research
                ),
            },
            "message": (
                f"Keyword research ready ({provider}"
                f"{'; Labs' if labs_ready else ''})."
                if configured
                else (
                    "Set KEYWORD_API_PROVIDER=dataforseo plus KEYWORD_API_LOGIN / "
                    "KEYWORD_API_PASSWORD to enable search volume research."
                )
            ),
        }

    def difficulty(self, keywords: list[str]) -> dict[str, Any]:
        cleaned = [k.strip() for k in keywords if k and str(k).strip()]
        if not cleaned:
            return {
                "status": "skipped",
                "is_real_research": False,
                "message": "No keywords provided.",
                "keywords": [],
            }
        if not self.labs.is_configured():
            return {
                "status": "unavailable",
                "is_real_research": False,
                "message": (
                    "DataForSEO Labs is not configured. Same login/password as "
                    "Keywords Data; set KEYWORD_LABS_ENABLED=true (default)."
                ),
                "keywords": [],
                "seed_keywords": cleaned,
            }
        try:
            mapping = self.labs.bulk_keyword_difficulty(cleaned)
            rows = [
                {
                    "keyword": kw,
                    "keyword_difficulty": mapping.get(kw.lower()),
                }
                for kw in cleaned
            ]
            return {
                "status": "ok",
                "provider": "dataforseo",
                "is_real_research": True,
                "source": "dataforseo_labs_bulk_keyword_difficulty",
                "location_code": self.settings.keywords.location_code,
                "language_code": self.settings.keywords.language_code,
                "message": f"Difficulty for {len(rows)} keyword(s) via DataForSEO Labs.",
                "seed_keywords": cleaned,
                "keywords": rows,
            }
        except DataForSeoError as exc:
            return {
                "status": "error",
                "provider": "dataforseo",
                "is_real_research": False,
                "message": str(exc),
                "seed_keywords": cleaned,
                "keywords": [],
            }

    def related(
        self,
        keyword: str,
        *,
        depth: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        seed = (keyword or "").strip()
        if not seed:
            return {
                "status": "skipped",
                "is_real_research": False,
                "message": "No seed keyword provided.",
                "related": [],
            }
        if not self.labs.is_configured():
            return {
                "status": "unavailable",
                "is_real_research": False,
                "message": "DataForSEO Labs is not configured.",
                "seed_keyword": seed,
                "related": [],
            }
        try:
            rows = self.labs.related_keywords(seed, depth=depth, limit=limit)
            return {
                "status": "ok",
                "provider": "dataforseo",
                "is_real_research": True,
                "source": "dataforseo_labs_related_keywords",
                "location_code": self.settings.keywords.location_code,
                "language_code": self.settings.keywords.language_code,
                "depth": depth
                if depth is not None
                else self.settings.keywords.related_depth,
                "message": (
                    f"Found {len(rows)} related keyword(s) for '{seed}' "
                    "via DataForSEO Labs."
                ),
                "seed_keyword": seed,
                "related": rows,
            }
        except DataForSeoError as exc:
            return {
                "status": "error",
                "provider": "dataforseo",
                "is_real_research": False,
                "message": str(exc),
                "seed_keyword": seed,
                "related": [],
            }

    def research(
        self,
        keywords: list[str],
        *,
        include_difficulty: bool = True,
        include_related: bool | None = None,
        related_depth: int | None = None,
        related_limit: int | None = None,
    ) -> dict[str, Any]:
        """Volume/CPC plus optional Labs difficulty + related ideas.

        Never invents metrics. Labs failures are recorded under `labs_errors`
        without failing the whole research when volume succeeded.
        """
        cleaned = [k.strip() for k in keywords if k and str(k).strip()]
        if not cleaned:
            return {
                "status": "skipped",
                "provider": (self.settings.keywords.provider or None),
                "is_real_research": False,
                "message": "No seed keywords provided for research.",
                "keywords": [],
            }

        if not self.is_configured():
            return {
                "status": "unavailable",
                "provider": (self.settings.keywords.provider or None),
                "is_real_research": False,
                "message": (
                    "KEYWORD RESEARCH NOT AVAILABLE: DataForSEO is not configured. "
                    "Set KEYWORD_API_PROVIDER=dataforseo, KEYWORD_API_LOGIN, and "
                    "KEYWORD_API_PASSWORD in SEO-Agent/.env."
                ),
                "keywords": [],
                "seed_keywords": cleaned,
            }

        provider = (self.settings.keywords.provider or "").lower()
        try:
            if provider != "dataforseo":
                return {
                    "status": "unavailable",
                    "provider": provider,
                    "is_real_research": False,
                    "message": (
                        f"Provider '{provider}' is not implemented yet. "
                        "Use KEYWORD_API_PROVIDER=dataforseo."
                    ),
                    "keywords": [],
                    "seed_keywords": cleaned,
                }

            rows = self.client.search_volume(cleaned)
            labs_errors: list[str] = []
            related_rows: list[dict[str, Any]] = []
            want_related = (
                self.settings.keywords.include_related_in_research
                if include_related is None
                else include_related
            )

            if include_difficulty and self.labs.is_configured():
                try:
                    difficulty_map = self.labs.bulk_keyword_difficulty(
                        [r["keyword"] for r in rows] or cleaned
                    )
                    for row in rows:
                        row["keyword_difficulty"] = difficulty_map.get(
                            str(row.get("keyword") or "").lower()
                        )
                except DataForSeoError as exc:
                    labs_errors.append(f"difficulty: {exc}")
                    for row in rows:
                        row.setdefault("keyword_difficulty", None)

            if want_related and self.labs.is_configured():
                try:
                    related_rows = self.labs.related_keywords(
                        cleaned[0],
                        depth=related_depth,
                        limit=related_limit,
                    )
                except DataForSeoError as exc:
                    labs_errors.append(f"related: {exc}")

            sources = ["dataforseo_keywords_data_google_ads_search_volume"]
            if include_difficulty and self.labs.is_configured():
                sources.append("dataforseo_labs_bulk_keyword_difficulty")
            if related_rows:
                sources.append("dataforseo_labs_related_keywords")

            log_event(
                logger,
                "keyword_research_completed",
                provider=provider,
                seeds=len(cleaned),
                results=len(rows),
                related=len(related_rows),
                labs_errors=len(labs_errors),
            )
            parts = [f"volume for {len(rows)} keyword(s)"]
            if any(r.get("keyword_difficulty") is not None for r in rows):
                parts.append("difficulty")
            if related_rows:
                parts.append(f"{len(related_rows)} related for '{cleaned[0]}'")
            return {
                "status": "ok",
                "provider": "dataforseo",
                "is_real_research": True,
                "source": "+".join(sources),
                "location_code": self.settings.keywords.location_code,
                "language_code": self.settings.keywords.language_code,
                "message": (
                    f"Researched via DataForSEO: {', '.join(parts)} "
                    f"(location={self.settings.keywords.location_code}, "
                    f"language={self.settings.keywords.language_code})."
                ),
                "seed_keywords": cleaned,
                "keywords": rows,
                "related": related_rows,
                "labs_errors": labs_errors,
            }
        except DataForSeoError as exc:
            log_event(logger, "keyword_research_failed", error=str(exc))
            return {
                "status": "error",
                "provider": provider,
                "is_real_research": False,
                "message": str(exc),
                "seed_keywords": cleaned,
                "keywords": [],
            }
        except Exception as exc:  # noqa: BLE001 — never break optimize/audit
            log_event(logger, "keyword_research_exception", error=str(exc))
            return {
                "status": "error",
                "provider": provider,
                "is_real_research": False,
                "message": f"Keyword research failed: {exc}",
                "seed_keywords": cleaned,
                "keywords": [],
            }
