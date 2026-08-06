from datetime import datetime, timezone

from app.models.audit import SiteAudit
from app.models.crawl import CrawlStats
from app.models.issues import Issue, Severity
from app.models.optimization import OptimizationResult, PageOptimization
from app.models.page import PageExtraction
from app.models.reports import ReportFormat
from app.reports.builder import build_report_document
from app.reports.markdown_report import render_markdown
from app.services.report_service import ReportService


def _sample_audit() -> SiteAudit:
    return SiteAudit(
        audit_id="audit-123",
        seed_url="https://example.com",
        created_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        score=88.0,
        pages=[
            PageExtraction(
                url="https://example.com",
                final_url="https://example.com",
                status_code=200,
                title="Example Domain",
                h1=["Example Domain"],
            )
        ],
        issues=[
            Issue(
                code="missing_meta_description",
                severity=Severity.WARNING,
                message="Page is missing a meta description",
                url="https://example.com",
            ),
            Issue(
                code="missing_title",
                severity=Severity.CRITICAL,
                message="Page is missing a title tag",
                url="https://example.com/x",
            ),
            Issue(
                code="missing_schema",
                severity=Severity.INFO,
                message="Page has no JSON-LD structured data",
                url="https://example.com",
            ),
        ],
        stats=CrawlStats(seed_url="https://example.com", pages_crawled=1),
        optimization=OptimizationResult(
            url="https://example.com",
            status="ok",
            pages=[
                PageOptimization(
                    url="https://example.com",
                    improved_title="Example Domain | Official Site",
                    keyword_suggestions=["example domain"],
                )
            ],
        ),
    )


def test_report_document_sections():
    doc = build_report_document(_sample_audit())
    assert doc.overall_seo_score == 88.0
    assert doc.summary.critical_count == 1
    assert doc.summary.warning_count == 1
    assert doc.summary.suggestion_count == 1
    assert len(doc.critical_issues) == 1
    assert len(doc.warnings) == 1
    assert len(doc.suggestions) == 1
    assert doc.page_overview


def test_markdown_contains_required_headings():
    md = render_markdown(_sample_audit())
    for heading in (
        "## Audit Scope",
        "## Summary",
        "## Critical Issues",
        "## Warnings",
        "## Suggestions",
        "## Recommendations",
        "## Overall SEO Score",
        "## AI Optimization Suggestions",
    ):
        assert heading in md
    assert "88.0/100" in md or "88.0 / 100" in md
    assert "missing_title" in md
    assert "SCOPE" in md or "analyzed" in md.lower()


def test_report_service_json_and_markdown(tmp_path):
    audit = _sample_audit()
    service = ReportService()

    md = service.generate(audit, ReportFormat.MARKDOWN, out_path=tmp_path / "r.md")
    assert md.path is not None
    assert "/" not in md.path or not md.path.startswith("/")  # relative / basename only
    assert (tmp_path / "r.md").read_text().startswith("# SEO Audit Report")
    assert md.metadata.get("delivery") in {"file_and_inline_content", "inline_content"}

    js = service.generate(audit, ReportFormat.JSON)
    assert '"overall_seo_score"' in js.content
    assert '"critical_issues"' in js.content
    assert js.document is not None


def test_pdf_not_implemented():
    service = ReportService()
    try:
        service.generate(_sample_audit(), ReportFormat.PDF)
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
