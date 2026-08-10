"""OAuth Production checklist helpers."""

from __future__ import annotations

from app.config.settings import GoogleSearchConsoleSettings
from app.integrations.google.oauth_production import (
    normalize_publishing_status,
    production_checklist,
)


def test_normalize_publishing_status():
    assert normalize_publishing_status("production") == "production"
    assert normalize_publishing_status("prod") == "production"
    assert normalize_publishing_status("testing") == "testing"
    assert normalize_publishing_status(None) == "testing"


def test_checklist_testing_blocks_customers():
    settings = GoogleSearchConsoleSettings(
        oauth_publishing_status="testing",
        redirect_uri="http://localhost:8000/auth/callback",
    )
    out = production_checklist(settings)
    assert out["publishing_status"] == "testing"
    assert out["customer_access"] == "test_users_only"
    assert out["production_ready"] is False
    assert out["blocking"]


def test_checklist_production_ready_with_https_urls():
    settings = GoogleSearchConsoleSettings(
        oauth_publishing_status="production",
        redirect_uri="https://seo.example.com/auth/callback",
        privacy_policy_url="https://seo.example.com/legal/privacy",
        homepage_url="https://seo.example.com/",
    )
    out = production_checklist(settings)
    assert out["production_ready"] is True
    assert out["customer_access"] == "any_google_account"
    assert out["blocking"] == []


def test_checklist_production_localhost_redirect_blocks():
    settings = GoogleSearchConsoleSettings(
        oauth_publishing_status="production",
        redirect_uri="http://localhost:8000/auth/callback",
        privacy_policy_url="https://seo.example.com/legal/privacy",
    )
    out = production_checklist(settings)
    assert out["production_ready"] is False
    assert any("localhost" in b for b in out["blocking"])
