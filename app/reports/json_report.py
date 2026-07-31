from __future__ import annotations

from app.models.audit import SiteAudit
from app.models.reports import ReportDocument
from app.reports.builder import build_report_document


def render_json(audit: SiteAudit, *, full_audit: bool = False) -> str:
    """Render report JSON. Default is structured ReportDocument sections."""
    if full_audit:
        return audit.model_dump_json(indent=2)
    document = build_report_document(audit)
    return document.model_dump_json(indent=2)


def render_document_json(document: ReportDocument) -> str:
    return document.model_dump_json(indent=2)
