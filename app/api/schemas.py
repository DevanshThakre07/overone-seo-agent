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


class OptimizeRequest(BaseModel):
    url: HttpUrl
    target_keywords: list[str] = Field(default_factory=list)


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
