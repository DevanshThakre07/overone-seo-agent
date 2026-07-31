from pathlib import Path

import pytest
import responses
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_job_runner
from app.api.jobs import InProcessJobRunner
from app.config import settings as settings_module

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    db_path = tmp_path / "api-audits.db"
    monkeypatch.setenv("SEO_STORAGE_PATH", str(db_path))
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()

    app = create_app()
    # Fresh runner per test app
    app.dependency_overrides[get_job_runner] = lambda: InProcessJobRunner(max_workers=1)

    with TestClient(app) as client:
        yield client

    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()


def _mock_example_site() -> None:
    html = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/", body=html, status=200)
    responses.add(responses.GET, "https://example.com", body=html, status=200)
    responses.add(responses.GET, "https://example.com/sample", body=html, status=200)
    responses.add(responses.GET, "https://example.com/about", body=html, status=200)


@responses.activate
def test_health_and_audit_history_report(api_client):
    _mock_example_site()

    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    audit_resp = api_client.post(
        "/audit",
        json={"url": "https://example.com/", "max_pages": 2, "save": True},
    )
    assert audit_resp.status_code == 200, audit_resp.text
    body = audit_resp.json()
    assert body["audit_id"]
    assert body["pages"] >= 1
    assert body["status"] == "completed"

    history = api_client.get("/history", params={"url": "https://example.com/"})
    assert history.status_code == 200
    assert history.json()["count"] >= 1

    report = api_client.get(f"/report/{body['audit_id']}", params={"format": "markdown"})
    assert report.status_code == 200
    assert "SEO Audit Report" in report.text


@responses.activate
def test_compare_endpoint(api_client):
    _mock_example_site()
    first = api_client.post(
        "/audit", json={"url": "https://example.com/", "max_pages": 1, "save": True}
    )
    assert first.status_code == 200

    second = api_client.post(
        "/compare", json={"url": "https://example.com/", "max_pages": 1, "save": True}
    )
    assert second.status_code == 200
    diff = second.json()
    assert diff["has_baseline"] is True
    assert diff["current_audit_id"]


@responses.activate
def test_optimize_without_key_returns_error(api_client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    settings_module.get_settings.cache_clear()
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(
        responses.GET,
        "https://example.com/",
        body="<html><head><title>T</title></head><body><h1>H</h1></body></html>",
        status=200,
    )
    resp = api_client.post("/optimize", json={"url": "https://example.com/"})
    assert resp.status_code == 400
    assert "OPENAI_API_KEY" in resp.json()["detail"]
