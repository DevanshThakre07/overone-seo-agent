from __future__ import annotations

from pathlib import Path

from app.config.settings import get_settings
from app.models.audit import SiteAudit
from app.models.reports import ReportArtifact, ReportFormat
from app.repositories.factory import get_audit_repository
from app.services.report_service import ReportService, default_pdf_out_path
from app.tools.audit_tool import audit_site


def generate_report(
    url: str | None = None,
    *,
    audit: SiteAudit | None = None,
    audit_id: str | None = None,
    format: str = "markdown",
    full_audit_json: bool = False,
    out: str | Path | None = None,
    max_pages: int | None = None,
    save: bool = False,
) -> ReportArtifact:
    """Hermes-ready tool: generate a SEO report for a URL, audit, or audit_id.

    For format=pdf, always writes a file (default data/reports/{audit_id}.pdf)
    so chat clients get a path instead of a huge base64 blob.
    """
    settings = get_settings()
    repository = get_audit_repository(settings)
    service = ReportService(repository=repository)

    fmt = ReportFormat(format.lower())

    if audit is not None:
        target = audit
    elif audit_id is not None:
        return _generate_with_pdf_default(
            service, audit_id=audit_id, fmt=fmt, out=out, full_audit_json=full_audit_json
        )
    elif url:
        target = audit_site(url, max_pages=max_pages, save=save)
    else:
        raise ValueError("One of url, audit, or audit_id is required")

    out_path = out
    if fmt == ReportFormat.PDF and out_path is None:
        out_path = default_pdf_out_path(target.audit_id)
    return service.generate(
        target, fmt, full_audit_json=full_audit_json, out_path=out_path
    )


def _generate_with_pdf_default(
    service: ReportService,
    *,
    audit_id: str,
    fmt: ReportFormat,
    out: str | Path | None,
    full_audit_json: bool,
) -> ReportArtifact:
    out_path = out
    if fmt == ReportFormat.PDF and out_path is None:
        out_path = default_pdf_out_path(audit_id)
    return service.generate_from_audit_id(
        audit_id, fmt, out_path=out_path
    )
