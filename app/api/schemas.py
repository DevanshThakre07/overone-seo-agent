from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class AuditRequest(BaseModel):
    url: HttpUrl
    max_pages: int | None = None
    max_depth: int | None = None
    save: bool = True
    compare: bool = False
    optimize: bool = False
    target_keywords: list[str] = Field(default_factory=list)
    optimize_max_pages: int | None = None
    background: bool = False
    # Customer's Connect Google account id (after they OAuth). Enables GSC data.
    gsc_account_id: str | None = None
    # None = auto-run PageSpeed when GOOGLE_PAGESPEED_API_KEY is set.
    pagespeed: bool | None = None
    # Authenticated crawl — in-memory only; ignored unless use_authenticated_crawl.
    auth_cookie: str | None = None
    auth_headers: dict[str, str] = Field(default_factory=dict)
    use_authenticated_crawl: bool = False
    # Phase 2 — opt-in paid competitive enrichment (never auto).
    include_serp: bool = False
    include_backlinks: bool = False
    # GA4 — opt-in; needs gsc_account_id. property_id optional if preference saved.
    include_ga4: bool = False
    ga4_property_id: str | None = None


class OptimizeRequest(BaseModel):
    url: HttpUrl
    target_keywords: list[str] = Field(default_factory=list)
    auth_cookie: str | None = None
    auth_headers: dict[str, str] = Field(default_factory=dict)
    use_authenticated_crawl: bool = False


class LoginWallRequest(BaseModel):
    url: HttpUrl


class ReportRequest(BaseModel):
    url: HttpUrl | None = None
    audit_id: str | None = None
    format: str = "markdown"
    max_pages: int | None = None
    save: bool = True


class HistoryQuery(BaseModel):
    url: HttpUrl
    limit: int = 20


class CompareRequest(BaseModel):
    url: HttpUrl
    max_pages: int | None = None
    save: bool = True


class AuditSummaryResponse(BaseModel):
    audit_id: str
    seed_url: str
    score: float
    pages: int
    issues: int
    summary: dict[str, Any] = Field(default_factory=dict)
    job_id: str | None = None
    status: str = "completed"


class JobResponse(BaseModel):
    job_id: str
    status: str
    result_type: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
