from app.models.diff import AuditDiff
from app.models.issues import Issue, Severity
from app.reports.diff_report import render_diff_json, render_diff_markdown


def test_diff_markdown_and_json():
    diff = AuditDiff(
        url="https://example.com",
        previous_audit_id="old",
        current_audit_id="new",
        previous_score=80,
        current_score=90,
        score_delta=10,
        new_issues=[
            Issue(
                code="missing_schema",
                severity=Severity.INFO,
                message="no schema",
                url="https://example.com",
            )
        ],
        resolved_issues=[],
        unchanged_issue_count=2,
        has_baseline=True,
        summary="Score improved by 10.0.",
    )
    md = render_diff_markdown(diff)
    assert "# SEO Audit Change Report" in md
    assert "## New Issues" in md
    assert "missing_schema" in md
    js = render_diff_json(diff)
    assert '"score_delta": 10.0' in js
