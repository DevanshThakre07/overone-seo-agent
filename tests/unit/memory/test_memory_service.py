from datetime import datetime, timezone, timedelta

from app.models.audit import SiteAudit
from app.models.issues import Issue, Severity
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.services.memory_service import MemoryService


def _audit(
    *,
    audit_id: str,
    score: float,
    issues: list[Issue],
    created_at: datetime,
    url: str = "https://example.com",
) -> SiteAudit:
    return SiteAudit(
        audit_id=audit_id,
        seed_url=url,
        created_at=created_at,
        score=score,
        issues=issues,
    )


def test_save_history_and_compare(tmp_path):
    repo = SqliteAuditRepository(str(tmp_path / "audits.db"))
    memory = MemoryService(repo)
    t0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=1)

    first = _audit(
        audit_id="a1",
        score=80,
        created_at=t0,
        issues=[
            Issue(
                code="missing_title",
                severity=Severity.CRITICAL,
                message="missing",
                url="https://example.com",
            ),
            Issue(
                code="missing_meta_description",
                severity=Severity.WARNING,
                message="meta",
                url="https://example.com",
            ),
        ],
    )
    memory.save(first)

    second = _audit(
        audit_id="a2",
        score=90,
        created_at=t1,
        issues=[
            Issue(
                code="missing_meta_description",
                severity=Severity.WARNING,
                message="meta",
                url="https://example.com",
            ),
            Issue(
                code="missing_schema",
                severity=Severity.INFO,
                message="schema",
                url="https://example.com",
            ),
        ],
    )

    # Compare against previous before saving current
    previous = memory.latest("https://example.com/")
    diff = memory.compare(second, previous=previous)
    memory.save(second)

    assert diff.has_baseline is True
    assert diff.previous_audit_id == "a1"
    assert diff.score_delta == 10.0
    assert any(i.code == "missing_schema" for i in diff.new_issues)
    assert any(i.code == "missing_title" for i in diff.resolved_issues)
    assert diff.unchanged_issue_count == 1

    history = memory.history("https://example.com", limit=10)
    assert len(history) == 2
    assert history[0].audit_id == "a2"


def test_compare_without_baseline(tmp_path):
    repo = SqliteAuditRepository(str(tmp_path / "audits.db"))
    memory = MemoryService(repo)
    current = _audit(
        audit_id="only",
        score=70,
        created_at=datetime.now(timezone.utc),
        issues=[],
    )
    diff = memory.compare(current)
    assert diff.has_baseline is False
    assert "No previous audit" in diff.summary


def test_url_normalization_for_lookup(tmp_path):
    repo = SqliteAuditRepository(str(tmp_path / "audits.db"))
    memory = MemoryService(repo)
    memory.save(
        _audit(
            audit_id="n1",
            score=50,
            created_at=datetime.now(timezone.utc),
            issues=[],
            url="https://Example.com/path/",
        )
    )
    assert memory.latest("https://example.com/path") is not None
