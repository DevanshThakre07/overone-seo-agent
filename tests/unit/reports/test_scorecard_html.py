"""FP-4 thin client scorecard HTML."""

from app.models.audit import SiteAudit
from app.models.issues import Issue, Severity
from app.reports.scorecard_html import render_scorecard_html


def test_scorecard_includes_score_and_issues():
    audit = SiteAudit(
        seed_url="https://actoro.app/",
        score=82.0,
        issues=[
            Issue(
                code="title_too_short",
                severity=Severity.WARNING,
                message="Title is short",
                url="https://actoro.app/",
            ),
            Issue(
                code="missing_canonical",
                severity=Severity.CRITICAL,
                message="Add a canonical",
                url="https://actoro.app/privacy",
            ),
        ],
        summary={
            "severity_counts": {"critical": 1, "warning": 1, "info": 0},
            "recommendations": [
                {
                    "url": "https://actoro.app/",
                    "actions": [
                        {
                            "code": "title_rewrite",
                            "message": 'Use a clearer title',
                        }
                    ],
                }
            ],
        },
    )
    html = render_scorecard_html(audit, token="abc123", expires_at="2099-01-01")
    assert "SEO Scorecard" in html
    assert "https://actoro.app/" in html
    assert "82" in html
    assert "missing_canonical" in html
    assert "Download PDF" in html
    assert "/share/abc123?format=pdf" in html
    assert "Use a clearer title" in html
