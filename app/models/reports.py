from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.diff import AuditDiff
from app.models.issues import Issue
from app.models.optimization import OptimizationResult


class ReportFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
    PDF = "pdf"


class ReportSummary(BaseModel):
    seed_url: str
    audit_id: str
    created_at: datetime | None = None
    pages_analyzed: int = 0
    overall_seo_score: float = 0.0
    critical_count: int = 0
    warning_count: int = 0
    suggestion_count: int = 0
    top_issue_codes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReportDocument(BaseModel):
    """Normalized report view shared by JSON and Markdown renderers."""

    summary: ReportSummary
    critical_issues: list[Issue] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    suggestions: list[Issue] = Field(default_factory=list)
    overall_seo_score: float = 0.0
    optimization: OptimizationResult | None = None
    diff: AuditDiff | None = None
    page_overview: list[dict[str, Any]] = Field(default_factory=list)


class ReportArtifact(BaseModel):
    audit_id: str
    format: ReportFormat
    content: str
    path: str | None = None
    document: ReportDocument | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
