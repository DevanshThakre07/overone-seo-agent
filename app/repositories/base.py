from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.audit import SiteAudit


@runtime_checkable
class AuditRepository(Protocol):
    def save(self, audit: SiteAudit) -> SiteAudit: ...

    def get(self, audit_id: str) -> SiteAudit | None: ...

    def list_by_url(self, url: str, *, limit: int = 20) -> list[SiteAudit]: ...

    def latest(self, url: str) -> SiteAudit | None: ...

    def previous(self, url: str, *, before_audit_id: str | None = None) -> SiteAudit | None: ...

    def delete(self, audit_id: str) -> bool: ...
