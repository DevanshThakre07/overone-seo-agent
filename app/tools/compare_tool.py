from __future__ import annotations

from pathlib import Path

from app.config.settings import get_settings
from app.models.diff import AuditDiff
from app.reports.diff_report import render_diff_json, render_diff_markdown
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.services.memory_service import MemoryService
from app.tools.audit_tool import audit_site


def compare_audits(
    url: str,
    *,
    max_pages: int | None = None,
    save: bool = True,
) -> AuditDiff:
    """Hermes-ready tool: audit a URL and compare against the previous stored audit."""
    current = audit_site(url, max_pages=max_pages, save=save, compare=True)
    if current.diff is None:
        settings = get_settings()
        repo = SqliteAuditRepository(settings.storage.path)
        return MemoryService(repo).compare(current)
    return current.diff


def generate_change_report(
    url: str,
    *,
    format: str = "markdown",
    max_pages: int | None = None,
    out: str | Path | None = None,
) -> str:
    """Run compare_audits and render a change report."""
    diff = compare_audits(url, max_pages=max_pages, save=True)
    content = (
        render_diff_json(diff)
        if format.lower() == "json"
        else render_diff_markdown(diff)
    )
    if out is not None:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
    return content
