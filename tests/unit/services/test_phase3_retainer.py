"""Phase 3 v1 — trends, schedules, share tokens, dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.audit import SiteAudit
from app.models.issues import Issue, Severity
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.repositories.sqlite_schedule_repository import SqliteScheduleRepository
from app.repositories.sqlite_share_repository import SqliteShareRepository
from app.services.dashboard_service import DashboardService
from app.services.memory_service import MemoryService


def _audit(url: str, score: float, *, critical: int = 0) -> SiteAudit:
    issues = [
        Issue(
            code="missing_h1",
            severity=Severity.CRITICAL,
            message=f"missing {i}",
            url=url,
        )
        for i in range(critical)
    ]
    return SiteAudit(
        seed_url=url,
        score=score,
        created_at=datetime.now(timezone.utc),
        issues=issues,
        summary={"severity": {"critical": critical, "warning": 1, "info": 0}},
    )


def test_trends_series(tmp_path):
    db = str(tmp_path / "a.db")
    repo = SqliteAuditRepository(db)
    mem = MemoryService(repo)
    url = "https://example.com/"
    mem.save(_audit(url, 70, critical=2))
    mem.save(_audit(url, 80, critical=1))
    trends = mem.trends(url, limit=10)
    assert trends["count"] == 2
    assert trends["points"][0]["score"] == 70
    assert trends["points"][-1]["score"] == 80
    assert trends["score_delta"] == 10.0
    assert trends["score_delta_span"] == 10.0
    assert trends["score_delta_vs_previous"] == 10.0


def test_trends_vs_previous_differs_from_span(tmp_path):
    db = str(tmp_path / "b.db")
    repo = SqliteAuditRepository(db)
    mem = MemoryService(repo)
    url = "https://example.com/span"
    mem.save(_audit(url, 50))
    mem.save(_audit(url, 90))
    mem.save(_audit(url, 80))
    trends = mem.trends(url, limit=10)
    assert trends["score_delta_span"] == 30.0  # 80 - 50
    assert trends["score_delta_vs_previous"] == -10.0  # 80 - 90

    db = str(tmp_path / "s.db")
    repo = SqliteScheduleRepository(db)
    row = repo.create("https://example.com/", every_hours=24)
    assert row["enabled"] is True
    assert row["next_run_at"]
    # Force due by rewriting next_run_at into the past
    with repo._connect() as conn:
        conn.execute(
            "UPDATE audit_schedules SET next_run_at = ? WHERE schedule_id = ?",
            ("2000-01-01T00:00:00+00:00", row["schedule_id"]),
        )
        conn.commit()
    due = repo.due()
    assert any(d["schedule_id"] == row["schedule_id"] for d in due)
    repo.mark_run(row["schedule_id"], audit_id="abc", error=None)
    updated = repo.get(row["schedule_id"])
    assert updated["last_audit_id"] == "abc"
    assert updated["last_error"] is None


def test_share_token(tmp_path):
    db = str(tmp_path / "share.db")
    audits = SqliteAuditRepository(db)
    shares = SqliteShareRepository(db)
    saved = audits.save(_audit("https://example.com/", 75))
    share = shares.create(saved.audit_id, days_valid=7)
    assert share["token"]
    got = shares.get(share["token"])
    assert got is not None
    assert got["expired"] is False
    assert got["audit_id"] == saved.audit_id


def test_dashboard_empty_and_ok(tmp_path, monkeypatch):
    db = str(tmp_path / "d.db")
    monkeypatch.setenv("SEO_STORAGE_PATH", db)
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()
    empty = DashboardService().build("https://example.com/")
    assert empty["status"] == "empty"

    repo = SqliteAuditRepository(db)
    MemoryService(repo).save(_audit("https://example.com/", 88, critical=0))
    settings_module.get_settings.cache_clear()
    filled = DashboardService().build("https://example.com/")
    assert filled["status"] == "ok"
    assert filled["latest"]["score"] == 88
    assert filled["audit"]["available"] is True
    assert "tools" in filled
    assert filled["serp"]["available"] is False  # blank without include_serp data
    assert filled["backlinks"]["available"] is False
    settings_module.get_settings.cache_clear()
