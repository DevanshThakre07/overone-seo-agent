from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.issues import Issue


class AuditDiff(BaseModel):
    url: str
    previous_audit_id: str | None = None
    current_audit_id: str
    previous_score: float | None = None
    current_score: float = 0.0
    score_delta: float = 0.0
    new_issues: list[Issue] = Field(default_factory=list)
    resolved_issues: list[Issue] = Field(default_factory=list)
    unchanged_issue_count: int = 0
    has_baseline: bool = False
    summary: str = ""
