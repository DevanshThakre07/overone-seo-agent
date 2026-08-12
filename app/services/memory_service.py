from __future__ import annotations

from typing import Any

from app.logging import get_logger, log_event
from app.models.audit import SiteAudit
from app.models.diff import AuditDiff
from app.models.issues import Issue
from app.repositories.base import AuditRepository
from app.utils.url import normalize_url

logger = get_logger(__name__)


class MemoryService:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    def save(self, audit: SiteAudit) -> SiteAudit:
        saved = self.repository.save(audit)
        log_event(
            logger,
            "audit_saved",
            audit_id=saved.audit_id,
            url=saved.seed_url,
            score=saved.score,
        )
        return saved

    def get(self, audit_id: str) -> SiteAudit | None:
        return self.repository.get(audit_id)

    def history(self, url: str, *, limit: int = 20) -> list[SiteAudit]:
        return self.repository.list_by_url(normalize_url(url), limit=limit)

    def latest(self, url: str) -> SiteAudit | None:
        return self.repository.latest(normalize_url(url))

    def trends(self, url: str, *, limit: int = 20) -> dict[str, Any]:
        """Score + severity series for retainer tracking (oldest → newest)."""
        seed = normalize_url(url)
        audits = list(reversed(self.history(seed, limit=max(1, min(limit, 100)))))
        points: list[dict[str, Any]] = []
        for audit in audits:
            severity = (audit.summary or {}).get("severity") or {}
            if not severity and audit.issues:
                severity = {
                    "critical": sum(1 for i in audit.issues if i.severity.value == "critical"),
                    "warning": sum(1 for i in audit.issues if i.severity.value == "warning"),
                    "info": sum(1 for i in audit.issues if i.severity.value == "info"),
                }
            points.append(
                {
                    "audit_id": audit.audit_id,
                    "created_at": audit.created_at.isoformat(),
                    "score": audit.score,
                    "issue_count": len(audit.issues),
                    "pages": len(audit.pages),
                    "critical": int(severity.get("critical") or 0),
                    "warning": int(severity.get("warning") or 0),
                    "info": int(severity.get("info") or 0),
                }
            )
        score_delta = None
        score_delta_vs_previous = None
        if len(points) >= 2:
            # Window span (oldest → newest in this series).
            score_delta = round(points[-1]["score"] - points[0]["score"], 1)
            # True "since previous" = last vs immediate prior point.
            score_delta_vs_previous = round(
                points[-1]["score"] - points[-2]["score"], 1
            )
        return {
            "url": seed,
            "count": len(points),
            "score_delta": score_delta,
            "score_delta_span": score_delta,
            "score_delta_vs_previous": score_delta_vs_previous,
            "points": points,
            "message": (
                f"{len(points)} audit(s) for trend."
                if points
                else "No saved audits for this URL. Run audit with save=true first."
            ),
        }

    def compare(
        self,
        current: SiteAudit,
        previous: SiteAudit | None = None,
    ) -> AuditDiff:
        """Compare current audit to a previous one.

        If previous is omitted, loads the latest stored audit for the same URL
        excluding the current audit_id (so save-before-compare still works).
        """
        if previous is None:
            previous = self.repository.previous(
                current.seed_url, before_audit_id=current.audit_id
            )

        if previous is None:
            diff = AuditDiff(
                url=normalize_url(current.seed_url),
                current_audit_id=current.audit_id,
                current_score=current.score,
                has_baseline=False,
                summary="No previous audit found for this URL.",
            )
            log_event(logger, "audit_compared", url=diff.url, has_baseline=False)
            return diff

        prev_keys = {_issue_key(i) for i in previous.issues}
        curr_keys = {_issue_key(i) for i in current.issues}
        new_issues = [i for i in current.issues if _issue_key(i) not in prev_keys]
        resolved = [i for i in previous.issues if _issue_key(i) not in curr_keys]
        unchanged = len(prev_keys & curr_keys)
        score_delta = current.score - previous.score

        if score_delta > 0:
            trend = f"Score improved by {score_delta:.1f}"
        elif score_delta < 0:
            trend = f"Score declined by {abs(score_delta):.1f}"
        else:
            trend = "Score unchanged"

        summary = (
            f"{trend}. New issues: {len(new_issues)}. "
            f"Resolved issues: {len(resolved)}. Unchanged: {unchanged}."
        )

        diff = AuditDiff(
            url=normalize_url(current.seed_url),
            previous_audit_id=previous.audit_id,
            current_audit_id=current.audit_id,
            previous_score=previous.score,
            current_score=current.score,
            score_delta=score_delta,
            new_issues=new_issues,
            resolved_issues=resolved,
            unchanged_issue_count=unchanged,
            has_baseline=True,
            summary=summary,
        )
        log_event(
            logger,
            "audit_compared",
            url=diff.url,
            has_baseline=True,
            score_delta=score_delta,
            new_issues=len(new_issues),
            resolved_issues=len(resolved),
        )
        return diff


def _issue_key(issue: Issue) -> tuple[str, str | None, str]:
    return (issue.code, issue.url, issue.message)
