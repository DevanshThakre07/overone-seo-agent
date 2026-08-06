from __future__ import annotations

from app.config.settings import get_settings
from app.models.audit import AuditOptions, SiteAudit
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.services.seo_service import SeoService


def audit_site(
    url: str,
    *,
    max_pages: int | None = None,
    max_depth: int | None = None,
    save: bool = False,
    compare: bool = False,
    optimize: bool = False,
    target_keywords: list[str] | None = None,
    optimize_max_pages: int | None = None,
    gsc_account_id: str | None = None,
    pagespeed: bool | None = None,
) -> SiteAudit:
    """Hermes-ready tool: run a full SEO audit and return SiteAudit."""
    settings = get_settings()
    repository = None
    if save or compare:
        repository = SqliteAuditRepository(settings.storage.path)

    service = SeoService(settings=settings, repository=repository)
    return service.run_audit(
        url,
        AuditOptions(
            max_pages=max_pages,
            max_depth=max_depth,
            save=save,
            compare=compare,
            optimize=optimize,
            target_keywords=target_keywords or [],
            optimize_max_pages=optimize_max_pages or settings.llm.optimize_max_pages,
            gsc_account_id=gsc_account_id,
            pagespeed=pagespeed,
        ),
    )
