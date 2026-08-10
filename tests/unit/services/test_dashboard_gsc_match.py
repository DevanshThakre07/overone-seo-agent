"""Dashboard GSC panel should say when verified sites don't match the audit URL."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.config.settings import Settings
from app.services.dashboard_service import DashboardService


def test_safe_gsc_flags_mismatch_for_unrelated_property():
    svc = DashboardService(Settings())
    fake = MagicMock()
    fake.status.return_value = {
        "connected": True,
        "email": "u@example.com",
        "has_analytics_scope": True,
    }
    fake.list_sites.return_value = {
        "sites": [{"site_url": "sc-domain:bookasto.com"}],
        "count": 1,
    }
    with patch(
        "app.integrations.google.service.GoogleSearchConsoleService",
        return_value=fake,
    ):
        out = svc._safe_gsc("demo", "https://actoro.app/")
    assert out["available"] is True
    data = out["data"]
    assert data["matches_audit_url"] is False
    assert data["matched_site_url"] is None
    assert "actoro.app" in (data["message"] or "")
    assert "bookasto.com" in " ".join(data["available_sites"] or [])


def test_safe_gsc_matches_domain_property():
    svc = DashboardService(Settings())
    fake = MagicMock()
    fake.status.return_value = {"connected": True, "email": "u@example.com"}
    fake.list_sites.return_value = {
        "sites": [{"site_url": "sc-domain:actoro.app"}],
        "count": 1,
    }
    with patch(
        "app.integrations.google.service.GoogleSearchConsoleService",
        return_value=fake,
    ):
        out = svc._safe_gsc("demo", "https://actoro.app/")
    assert out["data"]["matches_audit_url"] is True
    assert out["data"]["matched_site_url"] == "sc-domain:actoro.app"
