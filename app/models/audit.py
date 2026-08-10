from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.crawl import CrawlStats
from app.models.diff import AuditDiff
from app.models.issues import AnalyzerResult, Issue
from app.models.optimization import OptimizationResult
from app.models.page import PageExtraction


class AuditOptions(BaseModel):
    max_pages: int | None = None
    max_depth: int | None = None
    save: bool = False
    compare: bool = False
    optimize: bool = False
    target_keywords: list[str] = Field(default_factory=list)
    optimize_max_pages: int = 5
    # Customer id used for Connect Google / Search Console enrichment.
    gsc_account_id: str | None = None
    # Run PageSpeed Insights on the seed URL when an API key is configured.
    # None = auto (run if GOOGLE_PAGESPEED_API_KEY is set).
    pagespeed: bool | None = None
    # Authenticated crawl (Phase 1): in-memory only; never persisted.
    # Credentials are ignored unless use_authenticated_crawl is True (opt-in).
    auth_cookie: str | None = None
    auth_headers: dict[str, str] = Field(default_factory=dict)
    use_authenticated_crawl: bool = False
    # Phase 2 competitive enrichment — NEVER default on (paid DataForSEO calls).
    # include_serp requires target_keywords; include_backlinks uses seed host.
    include_serp: bool = False
    include_backlinks: bool = False
    # Phase A GA4 — opt-in; uses same Connect Google account_id as GSC.
    include_ga4: bool = False
    ga4_property_id: str | None = None


class SiteAudit(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    seed_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    score: float = 0.0
    pages: list[PageExtraction] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    analyzer_results: list[AnalyzerResult] = Field(default_factory=list)
    stats: CrawlStats | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    optimization: OptimizationResult | None = None
    diff: AuditDiff | None = None
