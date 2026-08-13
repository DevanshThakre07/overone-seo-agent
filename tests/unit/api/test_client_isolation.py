"""FP-6 lite — SEO_API_CLIENTS bind keys to account_id."""

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_job_runner
from app.api.jobs import InProcessJobRunner
from app.api.principals import parse_seo_api_clients
from app.config import settings as settings_module


@pytest.fixture()
def isolated_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEO_STORAGE_PATH", str(tmp_path / "iso.db"))
    monkeypatch.setenv("SEO_API_KEY", "admin-secret-key")
    monkeypatch.setenv(
        "SEO_API_CLIENTS",
        '{"demo":"demo-client-key","acme":"acme-client-key"}',
    )
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()

    app = create_app()
    app.dependency_overrides[get_job_runner] = lambda: InProcessJobRunner(max_workers=1)

    with TestClient(app) as client:
        yield client

    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()


def test_parse_seo_api_clients_json_and_pairs():
    assert parse_seo_api_clients('{"demo":"k1","acme":"k2"}') == {
        "demo": "k1",
        "acme": "k2",
    }
    assert parse_seo_api_clients("demo=k1,acme=k2") == {"demo": "k1", "acme": "k2"}
    assert parse_seo_api_clients("") == {}
    assert parse_seo_api_clients("not-json") == {}


def test_health_reports_client_isolation(isolated_client):
    health = isolated_client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["api_auth_required"] is True
    assert body["client_isolation"] is True


def test_auth_me_admin_and_client(isolated_client):
    denied = isolated_client.get("/auth/me")
    assert denied.status_code == 401

    admin = isolated_client.get(
        "/auth/me", headers={"X-API-Key": "admin-secret-key"}
    )
    assert admin.status_code == 200
    assert admin.json()["role"] == "admin"
    assert admin.json()["account_id"] is None

    client = isolated_client.get(
        "/auth/me", headers={"X-API-Key": "demo-client-key"}
    )
    assert client.status_code == 200
    assert client.json()["role"] == "client"
    assert client.json()["account_id"] == "demo"


def test_client_cannot_read_other_gsc_account(isolated_client):
    ok = isolated_client.get(
        "/auth/google/status",
        params={"account_id": "demo"},
        headers={"X-API-Key": "demo-client-key"},
    )
    assert ok.status_code == 200

    forbidden = isolated_client.get(
        "/auth/google/status",
        params={"account_id": "acme"},
        headers={"X-API-Key": "demo-client-key"},
    )
    assert forbidden.status_code == 403
    assert "bound to account_id" in forbidden.json()["detail"]


def test_admin_can_read_any_account(isolated_client):
    for aid in ("demo", "acme", "other"):
        resp = isolated_client.get(
            "/auth/google/status",
            params={"account_id": aid},
            headers={"Authorization": "Bearer admin-secret-key"},
        )
        assert resp.status_code == 200, resp.text


def test_dashboard_json_requires_key_ui_public(isolated_client):
    ui = isolated_client.get("/dashboard/ui")
    assert ui.status_code == 200

    denied = isolated_client.get(
        "/dashboard", params={"url": "https://example.com/"}
    )
    assert denied.status_code == 401

    ok = isolated_client.get(
        "/dashboard",
        params={"url": "https://example.com/", "gsc_account_id": "demo"},
        headers={"X-API-Key": "demo-client-key"},
    )
    assert ok.status_code == 200

    cross = isolated_client.get(
        "/dashboard",
        params={"url": "https://example.com/", "gsc_account_id": "acme"},
        headers={"X-API-Key": "demo-client-key"},
    )
    assert cross.status_code == 403


def test_client_schedule_bound_to_own_account(isolated_client):
    created = isolated_client.post(
        "/schedules",
        headers={"X-API-Key": "demo-client-key"},
        json={
            "url": "https://example.com/",
            "every_hours": 24,
            "gsc_account_id": "acme",  # spoof attempt
        },
    )
    assert created.status_code == 200
    assert created.json()["gsc_account_id"] == "demo"

    listed = isolated_client.get(
        "/schedules", headers={"X-API-Key": "acme-client-key"}
    )
    assert listed.status_code == 200
    assert listed.json()["schedules"] == []

    own = isolated_client.get(
        "/schedules", headers={"X-API-Key": "demo-client-key"}
    )
    assert len(own.json()["schedules"]) == 1
