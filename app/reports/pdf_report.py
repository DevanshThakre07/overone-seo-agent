"""PDF report renderer — Phase 3 placeholder."""

from __future__ import annotations

from app.models.audit import SiteAudit
from app.models.reports import ReportDocument


class PdfNotImplementedError(NotImplementedError):
    pass


def render_pdf(audit: SiteAudit) -> bytes:
    raise PdfNotImplementedError(
        "PDF reports are planned for a later milestone. Use json or markdown for now."
    )


def render_document_pdf(document: ReportDocument) -> bytes:
    raise PdfNotImplementedError(
        "PDF reports are planned for a later milestone. Use json or markdown for now."
    )
