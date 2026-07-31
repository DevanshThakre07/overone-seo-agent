"""Build a normalized ReportDocument from a SiteAudit."""

from __future__ import annotations

from collections import Counter

from app.models.audit import SiteAudit
from app.models.diff import AuditDiff
from app.models.issues import Severity
from app.models.reports import ReportDocument, ReportSummary


def build_report_document(audit: SiteAudit) -> ReportDocument:
    critical = [i for i in audit.issues if i.severity == Severity.CRITICAL]
    warnings = [i for i in audit.issues if i.severity == Severity.WARNING]
    suggestions = [i for i in audit.issues if i.severity == Severity.INFO]

    code_counts = Counter(i.code for i in audit.issues)
    top_codes = [code for code, _ in code_counts.most_common(5)]

    notes: list[str] = []
    if audit.optimization is not None:
        notes.append(f"AI optimization status: {audit.optimization.status}")
        if audit.optimization.message:
            notes.append(audit.optimization.message)
    if audit.diff is not None:
        notes.append(audit.diff.summary or "Comparison completed.")

    page_overview = [
        {
            "url": page.final_url,
            "status_code": page.status_code,
            "title": page.title,
            "title_source": page.title_source,
            "title_length": len(page.title) if page.title else 0,
            "meta_description": page.meta_description,
            "meta_description_length": (
                len(page.meta_description) if page.meta_description else 0
            ),
            "is_broken": page.is_broken,
            "h1": page.h1,
            "h1_count": len(page.h1),
            "h2_count": len(page.h2),
            "h3_count": len(page.h3),
            "image_count": page.image_count or len(page.images),
            "images_missing_alt": sum(
                1
                for img in page.images
                if img.alt is None or not str(img.alt).strip()
            ),
            "internal_links": len(page.internal_links),
            "internal_link_occurrences": page.internal_link_occurrences,
            "external_links": len(page.external_links),
            "external_link_occurrences": page.external_link_occurrences,
            "word_count": page.word_count,
            "canonical": page.canonical,
            "has_json_ld": page.has_json_ld,
            "schema_types": page.schema_types,
            "js_rendered": page.js_rendered,
            "extraction_warnings": page.extraction_warnings,
        }
        for page in audit.pages
    ]

    summary = ReportSummary(
        seed_url=audit.seed_url,
        audit_id=audit.audit_id,
        created_at=audit.created_at,
        pages_analyzed=len(audit.pages),
        overall_seo_score=audit.score,
        critical_count=len(critical),
        warning_count=len(warnings),
        suggestion_count=len(suggestions),
        top_issue_codes=top_codes,
        notes=notes,
    )

    return ReportDocument(
        summary=summary,
        critical_issues=critical,
        warnings=warnings,
        suggestions=suggestions,
        overall_seo_score=audit.score,
        optimization=audit.optimization,
        diff=audit.diff,
        page_overview=page_overview,
    )
