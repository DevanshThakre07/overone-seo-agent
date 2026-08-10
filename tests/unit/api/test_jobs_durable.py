"""Durable background audit jobs (SQLite fallback)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import responses
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_job_runner
from app.api.jobs import DurableJobRunner
from app.config import settings as settings_module
from app.repositories.factory import get_job_store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture()
def durable_client(tmp_path, monkeypatch):
    db_path = tmp_path / "durable.db"
    monkeypatch.setenv("SEO_STORAGE_PATH", str(db_path))
    monkeypatch.delenv("SEO_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SEO_API_KEY", "")
    monkeypatch.setenv("SEO_JOB_WORKERS", "1")
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()

    app = create_app()
    # Use real durable runner (no InProcess override)
    with TestClient(app) as client:
        yield client

    runner = get_job_runner()
    if hasattr(runner, "stop"):
        runner.stop()
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()


def _mock_site() -> None:
    html = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/", body=html, status=200)
    responses.add(responses.GET, "https://example.com", body=html, status=200)


@responses.activate
def test_background_audit_persists_and_completes(durable_client):
    _mock_site()

    resp = durable_client.post(
        "/audit",
        json={
            "url": "https://example.com/",
            "max_pages": 1,
            "save": True,
            "background": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    job_id = body["job_id"]
    assert job_id

    # Row exists in SQLite immediately
    store = get_job_store()
    record = store.get(job_id)
    assert record is not None
    assert record.status.value in {"pending", "running", "completed"}

    deadline = time.time() + 15
    final = None
    while time.time() < deadline:
        poll = durable_client.get(f"/jobs/{job_id}")
        assert poll.status_code == 200
        final = poll.json()
        if final["status"] in {"completed", "failed"}:
            break
        time.sleep(0.2)

    assert final is not None
    assert final["status"] == "completed", final
    assert final["result"]["audit_id"]
    assert final["result"]["score"] is not None


def test_durable_runner_survives_restart_simulation(tmp_path, monkeypatch):
    db = str(tmp_path / "restart.db")
    monkeypatch.setenv("SEO_STORAGE_PATH", db)
    monkeypatch.delenv("SEO_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()

    store = get_job_store()
    job_id = store.enqueue(
        result_type="audit",
        payload={
            "handler": "audit",
            "request": {
                "url": "https://example.com/",
                "max_pages": 1,
                "save": False,
            },
        },
    )

    # New runner on same DB sees pending job
    runner2 = DurableJobRunner(get_job_store(), max_workers=1)
    seen = runner2.get(job_id)
    assert seen is not None
    assert seen.status.value == "pending"

    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()
