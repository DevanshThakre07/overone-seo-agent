from datetime import datetime, timezone

import pytest

from app.models.audit import SiteAudit
from app.models.crawl import CrawlStats
from app.models.issues import Issue, Severity
from app.models.optimization import OptimizationResult, PageOptimization
from app.models.page import PageExtraction
from app.models.reports import ReportFormat
from app.reports.builder import build_report_document
from app.reports.markdown_report import render_markdown
from app.reports.pdf_report import PdfDependencyError, PDF_EXTRA_HINT
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


def _pdf_text(raw: bytes) -> str:
    import re
    import zlib

    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        data = match.group(1)
        try:
            data = zlib.decompress(data)
        except zlib.error:
            pass
        chunks.append(data.decode("latin-1", errors="replace"))
    return "\n".join(chunks)


def test_pdf_generates_valid_bytes(tmp_path):
    pytest.importorskip("fpdf")
    from app.reports.pdf_report import render_pdf

    audit = _sample_audit()
    raw = render_pdf(audit)
    assert raw.startswith(b"%PDF")
    assert len(raw) > 500
    text = _pdf_text(raw)
    assert "Optimize advice" in text
    assert "Example Domain | Official Site" in text

    service = ReportService()
    artifact = service.generate(audit, ReportFormat.PDF, out_path=tmp_path / "r.pdf")
    assert artifact.metadata.get("content_encoding") == "base64"
    assert artifact.metadata.get("media_type") == "application/pdf"
    assert (tmp_path / "r.pdf").read_bytes().startswith(b"%PDF")
    assert service.pdf_bytes(artifact).startswith(b"%PDF")


def test_pdf_omits_optimize_when_absent():
    pytest.importorskip("fpdf")
    from app.reports.pdf_report import render_pdf

    audit = _sample_audit()
    audit.optimization = None
    raw = render_pdf(audit)
    assert raw.startswith(b"%PDF")
    assert "Optimize advice" not in _pdf_text(raw)


def test_pdf_missing_dependency_message(monkeypatch):
    from app.reports import pdf_report

    def _boom():
        raise PdfDependencyError(PDF_EXTRA_HINT)

    monkeypatch.setattr(pdf_report, "_require_fpdf", _boom)
    with pytest.raises(PdfDependencyError, match="seo-agent\\[pdf\\]"):
        pdf_report.render_pdf(_sample_audit())
