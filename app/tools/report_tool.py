from __future__ import annotations

from pathlib import Path

from app.config.settings import get_settings
from app.models.audit import SiteAudit
from app.models.reports import ReportArtifact, ReportFormat
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.services.report_service import ReportService
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
    """Hermes-ready tool: generate a SEO report for a URL, audit, or audit_id."""
    settings = get_settings()
    repository = SqliteAuditRepository(settings.storage.path)
    service = ReportService(repository=repository)

    fmt = ReportFormat(format.lower())

    if audit is not None:
        return service.generate(
            audit, fmt, full_audit_json=full_audit_json, out_path=out
        )

    if audit_id is not None:
        return service.generate_from_audit_id(audit_id, fmt, out_path=out)

    if not url:
        raise ValueError("One of url, audit, or audit_id is required")

    loaded = audit_site(url, max_pages=max_pages, save=save)
    return service.generate(
        loaded, fmt, full_audit_json=full_audit_json, out_path=out
    )
