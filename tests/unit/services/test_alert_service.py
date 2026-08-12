"""Unit tests for monitoring alert triggers."""

from __future__ import annotations

from app.config.settings import AlertSettings, Settings
from app.services.alert_service import AlertService


def _svc(**alert_kw) -> AlertService:
    settings = Settings()
    settings.alerts = AlertSettings(webhook_url="https://example.com/hook", **alert_kw)
    return AlertService(settings)


def test_score_drop_trigger():
    svc = _svc(score_drop_threshold=5.0)
    result = {
        "score": 72.0,
        "seed_url": "https://actoro.app/",
        "summary": {
            "compare": {
                "has_baseline": True,
                "score_delta": -9.0,
                "new_issues": 0,
            }
        },
        "audit": {"diff": {"new_issues": []}},
    }
    triggers = svc.build_triggers(result, score_drop_threshold=5.0)
    assert any(t["type"] == "score_drop" for t in triggers)
    assert triggers[0]["score_delta"] == -9.0


def test_score_drop_below_threshold_ignored():
    svc = _svc()
    result = {
        "score": 80.0,
        "summary": {
            "compare": {"has_baseline": True, "score_delta": -2.0}
        },
        "audit": {"diff": {"new_issues": []}},
    }
    assert svc.build_triggers(result, score_drop_threshold=5.0) == []


def test_new_critical_trigger():
    svc = _svc()
    result = {
        "score": 88.0,
        "summary": {"compare": {"has_baseline": True, "score_delta": 1.0}},
        "audit": {
            "diff": {
                "new_issues": [
                    {
                        "code": "missing_title",
                        "severity": "critical",
                        "message": "Missing title",
                        "url": "https://x.com/",
                    },
                    {
                        "code": "missing_alt",
                        "severity": "warning",
                        "message": "alt",
                    },
                ]
            }
        },
    }
    triggers = svc.build_triggers(result, on_new_critical=True)
    crits = [t for t in triggers if t["type"] == "new_critical"]
    assert len(crits) == 1
    assert crits[0]["code"] == "missing_title"


def test_skip_without_webhook(tmp_path):
    settings = Settings()
    settings.alerts = AlertSettings(webhook_url=None)
    settings.storage.path = str(tmp_path / "audits.db")
    svc = AlertService(settings)
    out = svc.evaluate_and_notify(
        {
            "score": 50,
            "seed_url": "https://example.com/",
            "summary": {"compare": {"has_baseline": True, "score_delta": -20}},
            "audit": {"diff": {"new_issues": []}},
        }
    )
    assert out["status"] == "skipped"
    st = svc.status()
    assert st["last"] is not None
    assert st["last"]["fired"] is False
    assert st["last"]["reason"] == "webhook_not_configured"


def test_remember_last_on_fire(tmp_path, monkeypatch):
    settings = Settings()
    settings.alerts = AlertSettings(webhook_url="https://example.com/hook")
    settings.storage.path = str(tmp_path / "audits.db")
    svc = AlertService(settings)

    def fake_post(url, payload, *, timeout):
        return {"ok": True, "status_code": 200}

    monkeypatch.setattr(svc, "_post_webhook", fake_post)
    out = svc.evaluate_and_notify(
        {
            "audit_id": "a1",
            "score": 50,
            "seed_url": "https://example.com/",
            "summary": {"compare": {"has_baseline": True, "score_delta": -20}},
            "audit": {"diff": {"new_issues": []}},
        }
    )
    assert out["fired"] is True
    st = svc.status()
    assert st["last"]["fired"] is True
    assert "score_drop" in (st["last"]["trigger_types"] or [])
    assert st["last"]["delivery"]["ok"] is True
