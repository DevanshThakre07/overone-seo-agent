"""Rank history repository + service tests."""

from __future__ import annotations

from app.repositories.sqlite_rank_history_repository import SqliteRankHistoryRepository
from app.services.rank_history_service import RankHistoryService


def test_rank_history_records_and_lists(tmp_path):
    db = str(tmp_path / "ranks.db")
    repo = SqliteRankHistoryRepository(db)
    svc = RankHistoryService(repo)

    check = {
        "status": "ok",
        "provider": "dataforseo",
        "keyword": "Actor Booking",
        "device": "desktop",
        "rank": {
            "found": True,
            "target": "actoro.app",
            "position": 12,
            "rank_absolute": 12,
            "url": "https://actoro.app/",
            "title": "Actoro",
        },
        "top_organic": [{"rank_group": 1, "domain": "example.com"}],
        "message": "Rank #12",
    }
    saved = svc.record_check_result(
        check,
        seed_url="https://actoro.app/",
        audit_id="audit-1",
        source="audit_serp",
    )
    assert saved is not None
    assert saved["keyword"] == "actor booking"
    assert saved["position"] == 12
    assert saved["found"] is True

    # Second snapshot — improved
    check2 = dict(check)
    check2["rank"] = dict(check["rank"], position=7, rank_absolute=7)
    svc.record_check_result(check2, seed_url="https://actoro.app/", source="rank_check")

    hist = svc.history(url="https://actoro.app/", limit=10)
    assert hist["status"] == "ok"
    assert hist["count"] == 2
    series = hist["series"]["actor booking"]
    assert len(series) == 2
    assert series[0]["position"] == 12
    assert series[1]["position"] == 7

    filtered = svc.history(url="https://actoro.app/", keyword="actor booking")
    assert filtered["count"] == 2


def test_rank_history_skips_non_ok():
    class _Boom:
        def record(self, row):  # pragma: no cover
            raise AssertionError("should not record")

    svc = RankHistoryService(_Boom())
    assert svc.record_check_result({"status": "error"}, seed_url="https://x.com/") is None
    assert svc.record_serp_block({"status": "skipped"}, seed_url="https://x.com/") == []


def test_record_serp_block(tmp_path):
    repo = SqliteRankHistoryRepository(str(tmp_path / "r.db"))
    svc = RankHistoryService(repo)
    block = {
        "status": "ok",
        "seed_url": "https://actoro.app/",
        "target_domain": "actoro.app",
        "checks": [
            {
                "status": "ok",
                "keyword": "ai actor",
                "provider": "dataforseo",
                "rank": {
                    "found": False,
                    "target": "actoro.app",
                    "position": None,
                },
            }
        ],
    }
    rows = svc.record_serp_block(block, seed_url="https://actoro.app/", audit_id="a1")
    assert len(rows) == 1
    assert rows[0]["found"] is False
