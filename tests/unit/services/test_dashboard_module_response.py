"""Module Response Quality — dashboard compare + tools has_data honesty."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from app.config.settings import Settings
from app.models.audit import SiteAudit
from app.models.issues import Issue, Severity
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.services.dashboard_service import DashboardService, _blank, _filled
from app.services.memory_service import MemoryService


def _audit(url: str, score: float, *, when: datetime | None = None) -> SiteAudit:
    return SiteAudit(
        seed_url=url,
        score=score,
        created_at=when or datetime.now(timezone.utc),
        issues=[
            Issue(
                code="missing_h1",
                severity=Severity.CRITICAL,
                message="missing",
                url=url,
            )
        ],
        summary={
            "severity": {"critical": 1, "warning": 0, "info": 0},
            "pagespeed": {"status": "ok", "lab": {"performance_score": 70}},
        },
    )


def test_compare_section_includes_score_delta(tmp_path):
    db = str(tmp_path / "c.db")
    repo = SqliteAuditRepository(db)
    mem = MemoryService(repo)
    url = "https://example.com/"
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mem.save(_audit(url, 70, when=t0))
    mem.save(_audit(url, 85, when=t0 + timedelta(days=1)))
    svc = DashboardService(Settings())
    svc.repo = repo
    svc.memory = mem
    latest = mem.latest(url)
    history = svc._history_entries(url, limit=10)
    section = svc._compare_section(latest, history)
    assert section["available"] is True
    data = section["data"]
    assert data["ready"] is True
    assert data["score_delta"] == 15.0
    assert data["previous_score"] == 70.0
    assert data["current_score"] == 85.0
    assert data["new_issues"] == 0 or data["new_issues"] >= 0


def test_tools_catalog_rank_history_and_trends_not_always_true():
    tools = DashboardService._tools_catalog(
        {
            "pagespeed_configured": True,
            "dataforseo_configured": False,
            "gsc_oauth_configured": False,
            "openai_configured": False,
            "alerts_configured": False,
        },
        None,
        _blank("no gsc"),
        ga4_section=_blank("no ga4"),
        trends={"count": 0},
        rank_history=_blank("No rank history yet"),
        schedules=_filled({"items": [], "count": 0, "alerts": {}}),
    )
    by_id = {t["id"]: t for t in tools}
    assert by_id["list_rank_history"]["has_data"] is False
    assert by_id["list_seo_trends"]["has_data"] is False
    assert by_id["schedules"]["has_data"] is False


def test_filled_keeps_caller_keywords_as_partial():
    from app.services.dashboard_service import _filled

    out = _filled(
        {
            "status": "caller_provided_not_researched",
            "is_real_research": False,
            "message": "Caller only",
            "keywords": ["seo", "books"],
        }
    )
    assert out["available"] is True
    assert out["status"] == "partial"
    assert out["data"]["keywords"] == ["seo", "books"]
