"""Tests for Google OAuth + Search Console integration (no live Google calls)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import GoogleSearchConsoleSettings
from app.integrations.google.oauth import (
    GoogleOAuthError,
    build_authorization_url,
    exchange_code_for_tokens,
    load_oauth_credentials,
)
from app.integrations.google.search_console import SearchConsoleClient
from app.integrations.google.service import GoogleSearchConsoleService, _match_site
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
def gsc_settings(secrets_file: Path, tmp_path: Path) -> GoogleSearchConsoleSettings:
    return GoogleSearchConsoleSettings(
        client_secrets_file=str(secrets_file),
        redirect_uri="http://localhost:8000/auth/callback",
        token_db_path=str(tmp_path / "tokens.db"),
    )


class TestOAuth:
    def test_load_credentials_from_json(self, gsc_settings):
        creds = load_oauth_credentials(gsc_settings)
        assert creds.client_id.endswith("apps.googleusercontent.com")
        assert creds.client_secret == "test-secret"

    def test_missing_secrets_raise(self, tmp_path):
        settings = GoogleSearchConsoleSettings(
            client_secrets_file=str(tmp_path / "missing.json"),
            client_id=None,
            client_secret=None,
        )
        with pytest.raises(GoogleOAuthError):
            load_oauth_credentials(settings)

    def test_authorization_url_contains_offline_consent(self, gsc_settings):
        creds = load_oauth_credentials(gsc_settings)
        url = build_authorization_url(creds, state="abc123")
        assert "accounts.google.com" in url
        assert "access_type=offline" in url
        assert "prompt=select_account%20consent" in url or "prompt=select_account+consent" in url
        assert "state=abc123" in url
        assert "webmasters.readonly" in url
        assert "analytics.readonly" in url
        assert "access_type=offline" in url

    def test_exchange_code_stores_refresh_token(self, gsc_settings):
        creds = load_oauth_credentials(gsc_settings)
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = {
            "access_token": "ya29.access",
            "refresh_token": "1//refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/webmasters.readonly",
        }
        with patch(
            "app.integrations.google.oauth.requests.post", return_value=fake
        ), patch(
            "app.integrations.google.oauth._fetch_email", return_value="user@example.com"
        ):
            tokens = exchange_code_for_tokens(creds, "auth-code")
        assert tokens.access_token == "ya29.access"
        assert tokens.refresh_token == "1//refresh"
        assert tokens.email == "user@example.com"


class TestTokenStore:
    def test_state_roundtrip_and_expiry(self, tmp_path):
        store = GoogleTokenStore(str(tmp_path / "t.db"))
        store.save_pending_state("state-1", "customer-a")
        assert store.consume_pending_state("state-1") == "customer-a"
        assert store.consume_pending_state("state-1") is None

    def test_connection_keeps_old_refresh_token(self, tmp_path):
        store = GoogleTokenStore(str(tmp_path / "t.db"))
        store.upsert_connection(
            account_id="c1",
            access_token="a1",
            refresh_token="r1",
            expires_in=3600,
            email="a@b.com",
        )
        store.upsert_connection(
            account_id="c1",
            access_token="a2",
            refresh_token=None,
            expires_in=3600,
        )
        conn = store.get_connection("c1")
        assert conn is not None
        assert conn.access_token == "a2"
        assert conn.refresh_token == "r1"
        assert conn.email == "a@b.com"


class TestSearchConsoleClient:
    def test_performance_snapshot_finds_opportunities(self):
        client = SearchConsoleClient("token")

        def fake_analytics(site_url, **kwargs):
            dims = kwargs.get("dimensions") or []
            if dims == ["query"]:
                return {
                    "rows": [
                        {
                            "keys": ["active learning"],
                            "clicks": 10,
                            "impressions": 200,
                            "ctr": 0.05,
                            "position": 8.1,
                        }
                    ]
                }
            if dims == ["page"]:
                return {
                    "rows": [
                        {
                            "keys": ["https://example.com/"],
                            "clicks": 12,
                            "impressions": 300,
                            "ctr": 0.04,
                            "position": 7.0,
                        }
                    ]
                }
            return {
                "rows": [
                    {
                        "keys": ["active learning", "https://example.com/"],
                        "clicks": 5,
                        "impressions": 120,
                        "ctr": 0.04,
                        "position": 14.2,
                    },
                    {
                        "keys": ["boring", "https://example.com/about"],
                        "clicks": 1,
                        "impressions": 10,
                        "ctr": 0.1,
                        "position": 3.0,
                    },
                    {
                        "keys": ["weak snippet", "https://example.com/"],
                        "clicks": 1,
                        "impressions": 200,
                        "ctr": 0.005,
                        "position": 2.0,
                    },
                ]
            }

        with patch.object(client, "search_analytics", side_effect=fake_analytics):
            snap = client.performance_snapshot("https://example.com/")
        assert snap["status"] == "ok"
        assert snap["opportunity_count"] == 2
        kinds = {o["kind"] for o in snap["opportunities"]}
        assert kinds == {"page2", "low_ctr"}
        assert snap["opportunities"][0]["query"] in {"active learning", "weak snippet"}
        assert snap["top_queries"][0]["query"] == "active learning"


class TestSiteMatching:
    def test_domain_property_match(self):
        sites = [{"site_url": "sc-domain:example.com"}]
        assert _match_site("https://www.example.com/pricing", sites) == "sc-domain:example.com"

    def test_url_prefix_match(self):
        sites = [{"site_url": "https://example.com/"}]
        assert _match_site("https://example.com/blog", sites) == "https://example.com/"


class TestServiceFlow:
    def test_start_and_complete_connect(self, gsc_settings):
        from app.config.settings import Settings

        settings = Settings(gsc=gsc_settings)
        # Avoid loading full YAML defaults overwriting our tmp paths.
        settings.gsc = gsc_settings
        service = GoogleSearchConsoleService(settings)

        started = service.start_connect("customer-42")
        assert "accounts.google.com" in started["authorization_url"]
        state = started["state"]

        fake_tokens = MagicMock()
        fake_tokens.access_token = "access"
        fake_tokens.refresh_token = "refresh"
        fake_tokens.expires_in = 3600
        fake_tokens.email = "client@example.com"
        fake_tokens.scope = "webmasters.readonly"

        with patch(
            "app.integrations.google.service.exchange_code_for_tokens",
            return_value=fake_tokens,
        ):
            result = service.complete_connect(code="code", state=state)

        assert result["status"] == "connected"
        assert result["account_id"] == "customer-42"
        status = service.status("customer-42")
        assert status["connected"] is True
        assert status["email"] == "client@example.com"
        assert status["oauth_publishing_status"] == "testing"
        assert status["customer_access"] == "test_users_only"
        prod = service.production_status()
        assert prod["publishing_status"] == "testing"
        assert "steps" in prod

    def test_audit_enrichment_skipped_without_account(self, gsc_settings):
        from app.config.settings import Settings

        settings = Settings(gsc=gsc_settings)
        settings.gsc = gsc_settings
        service = GoogleSearchConsoleService(settings)
        out = service.audit_enrichment(None, "https://example.com/")
        assert out["status"] == "skipped"
