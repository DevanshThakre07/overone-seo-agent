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
