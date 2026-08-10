"""GA4 Admin/Data clients + service (mocked HTTP)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import GoogleSearchConsoleSettings, Settings
from app.integrations.google.analytics_admin import AnalyticsAdminClient
from app.integrations.google.analytics_data import AnalyticsDataClient
from app.integrations.google.ga4_service import Ga4Service
from app.integrations.google.oauth import GoogleOAuthError
from app.integrations.google.token_store import GoogleTokenStore


@pytest.fixture
def secrets_file(tmp_path: Path) -> Path:
    path = tmp_path / "google-oauth-client.json"
    path.write_text(
        json.dumps(
            {
                "web": {
                    "client_id": "test-client.apps.googleusercontent.com",
                    "client_secret": "test-secret",
                    "redirect_uris": ["http://localhost:8000/auth/callback"],
                }
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def settings(secrets_file: Path, tmp_path: Path) -> Settings:
    s = Settings()
    s.gsc = GoogleSearchConsoleSettings(
        client_secrets_file=str(secrets_file),
        redirect_uri="http://localhost:8000/auth/callback",
        token_db_path=str(tmp_path / "tokens.db"),
    )
    return s


def test_admin_list_properties_flattens():
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {
        "accountSummaries": [
            {
                "account": "accounts/1",
                "displayName": "Acme",
                "propertySummaries": [
                    {
                        "property": "properties/999",
                        "displayName": "Acme Web",
                        "propertyType": "PROPERTY_TYPE_ORDINARY",
                    }
                ],
            }
        ]
    }
    with patch(
        "app.integrations.google.analytics_admin.requests.get", return_value=fake
    ):
        rows = AnalyticsAdminClient("tok").list_properties()
    assert rows[0]["property_id"] == "999"
    assert rows[0]["display_name"] == "Acme Web"
    assert rows[0]["account_name"] == "Acme"


def test_data_performance_snapshot_parses():
    totals = MagicMock()
    totals.status_code = 200
    totals.json.return_value = {
        "metricHeaders": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "screenPageViews"},
        ],
        "rows": [
            {
                "metricValues": [
                    {"value": "100"},
                    {"value": "80"},
                    {"value": "250"},
                ]
            }
        ],
    }
    pages = MagicMock()
    pages.status_code = 200
    pages.json.return_value = {
        "dimensionHeaders": [{"name": "pagePath"}],
        "metricHeaders": [
            {"name": "screenPageViews"},
            {"name": "sessions"},
            {"name": "totalUsers"},
        ],
        "rows": [
            {
                "dimensionValues": [{"value": "/"}],
                "metricValues": [
                    {"value": "50"},
                    {"value": "40"},
                    {"value": "30"},
                ],
            }
        ],
    }
    with patch(
        "app.integrations.google.analytics_data.requests.post",
        side_effect=[totals, pages],
    ):
        snap = AnalyticsDataClient("tok").performance_snapshot("999", days=7, top_n=5)
    assert snap["totals"]["sessions"] == 100
    assert snap["top_pages"][0]["page_path"] == "/"
    assert snap["property_id"] == "999"
    assert snap["has_data"] is True


def test_ga4_requires_analytics_scope(settings):
    store = GoogleTokenStore(settings.gsc.token_db_path)
    store.upsert_connection(
        account_id="cust",
        access_token="ya29.x",
        refresh_token="1//r",
        expires_in=3600,
        email="u@example.com",
        scopes="https://www.googleapis.com/auth/webmasters.readonly",
    )
    ga4 = Ga4Service(settings)
    status = ga4.status("cust")
    assert status["connected"] is True
    assert status["has_analytics_scope"] is False
    assert status["ga4_ready"] is False
    with pytest.raises(GoogleOAuthError, match="Analytics"):
        ga4.list_properties("cust")


def test_ga4_audit_enrichment_requires_property(settings):
    store = GoogleTokenStore(settings.gsc.token_db_path)
    store.upsert_connection(
        account_id="cust",
        access_token="ya29.x",
        refresh_token="1//r",
        expires_in=3600,
        email="u@example.com",
        scopes=(
            "https://www.googleapis.com/auth/webmasters.readonly "
            "https://www.googleapis.com/auth/analytics.readonly"
        ),
    )
    out = Ga4Service(settings).audit_enrichment("cust", None)
    assert out["status"] == "skipped"
    assert "preference" in out["message"].lower() or "ga4_property_id" in out["message"]


def test_ga4_preference_roundtrip_and_audit_uses_saved(settings):
    store = GoogleTokenStore(settings.gsc.token_db_path)
    store.upsert_connection(
        account_id="cust",
        access_token="ya29.x",
        refresh_token="1//r",
        expires_in=3600,
        email="u@example.com",
        scopes=(
            "https://www.googleapis.com/auth/webmasters.readonly "
            "https://www.googleapis.com/auth/analytics.readonly"
        ),
    )
    ga4 = Ga4Service(settings)
    fake_list = MagicMock()
    fake_list.status_code = 200
    fake_list.json.return_value = {
        "accountSummaries": [
            {
                "account": "accounts/1",
                "displayName": "Acme",
                "propertySummaries": [
                    {
                        "property": "properties/533500924",
                        "displayName": "actoro-c6be4",
                        "propertyType": "PROPERTY_TYPE_ORDINARY",
                    }
                ],
            }
        ]
    }
    with patch(
        "app.integrations.google.analytics_admin.requests.get",
        return_value=fake_list,
    ):
        saved = ga4.set_preferred_property_id("cust", "533500924")
    assert saved["status"] == "saved"
    assert ga4.get_preferred_property_id("cust") == "533500924"
    assert ga4.resolve_property_id("cust", None) == "533500924"
    assert ga4.resolve_property_id("cust", "111") == "111"

    # Reconnect must not wipe preference
    store.upsert_connection(
        account_id="cust",
        access_token="ya29.y",
        refresh_token="1//r2",
        expires_in=3600,
        email="u@example.com",
        scopes=(
            "https://www.googleapis.com/auth/webmasters.readonly "
            "https://www.googleapis.com/auth/analytics.readonly"
        ),
    )
    assert ga4.get_preferred_property_id("cust") == "533500924"

    with patch.object(
        ga4,
        "report",
        return_value={"has_data": True, "totals": {"sessions": 1}, "message": None},
    ):
        out = ga4.audit_enrichment("cust", None)
    assert out["status"] == "ok"
    assert out["property_id"] == "533500924"
    assert out["used_saved_preference"] is True


def test_ga4_list_properties_when_scoped(settings):
    store = GoogleTokenStore(settings.gsc.token_db_path)
    store.upsert_connection(
        account_id="cust",
        access_token="ya29.x",
        refresh_token="1//r",
        expires_in=3600,
        email="u@example.com",
        scopes=(
            "https://www.googleapis.com/auth/webmasters.readonly "
            "https://www.googleapis.com/auth/analytics.readonly"
        ),
    )
    fake = MagicMock()
    fake.status_code = 200
    fake.json.return_value = {
        "accountSummaries": [
            {
                "account": "accounts/1",
                "displayName": "Acme",
                "propertySummaries": [
                    {"property": "properties/42", "displayName": "Site"}
                ],
            }
        ]
    }
    with patch(
        "app.integrations.google.analytics_admin.requests.get", return_value=fake
    ):
        out = Ga4Service(settings).list_properties("cust")
    assert out["count"] == 1
    assert out["properties"][0]["property_id"] == "42"
