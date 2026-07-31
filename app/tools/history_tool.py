from __future__ import annotations

from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.services.memory_service import MemoryService
from app.utils.url import normalize_url


class HistoryEntry(BaseModel):
    audit_id: str
    seed_url: str
    created_at: str
    score: float
    issue_count: int
    pages: int


class HistoryResult(BaseModel):
    url: str
    count: int
    audits: list[HistoryEntry] = Field(default_factory=list)


def list_history(url: str, *, limit: int = 20) -> HistoryResult:
    """Hermes-ready tool: list previous audits for a URL."""
    settings = get_settings()
    repo = SqliteAuditRepository(settings.storage.path)
    audits = MemoryService(repo).history(url, limit=limit)
    entries = [
        HistoryEntry(
            audit_id=a.audit_id,
            seed_url=a.seed_url,
            created_at=a.created_at.isoformat(),
            score=a.score,
            issue_count=len(a.issues),
            pages=len(a.pages),
        )
        for a in audits
    ]
    return HistoryResult(url=normalize_url(url), count=len(entries), audits=entries)
