"""Scheduled audits enqueue durable jobs (Phase 4A-F)."""

from __future__ import annotations

from pathlib import Path

import pytest
import responses
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_job_runner
from app.config import settings as settings_module
from app.repositories.factory import get_job_store, get_schedule_repository
from app.services.schedule_service import ScheduleService

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture()
def sched_env(tmp_path, monkeypatch):
    db = str(tmp_path / "sched.db")
    monkeypatch.setenv("SEO_STORAGE_PATH", db)
    monkeypatch.delenv("SEO_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SEO_API_KEY", "")
    monkeypatch.setenv("SEO_JOB_WORKERS", "1")
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()
    yield db
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()


def test_mark_enqueued_and_set_last_result(sched_env):
    repo = get_schedule_repository()
    row = repo.create("https://example.com/", every_hours=24)
    repo.mark_enqueued(row["schedule_id"], job_id="job-1")
    got = repo.get(row["schedule_id"])
    assert got["last_job_id"] == "job-1"
    assert got["last_audit_id"] is None
    next_after = got["next_run_at"]

    repo.set_last_result(row["schedule_id"], audit_id="audit-9", error=None)
    got2 = repo.get(row["schedule_id"])
    assert got2["last_audit_id"] == "audit-9"
    assert got2["next_run_at"] == next_after


def test_run_due_queues_job(sched_env, monkeypatch):
    settings_module.get_settings.cache_clear()
    get_job_runner.cache_clear()

    svc = ScheduleService()
    row = svc.create("https://example.com/", every_hours=24)
    with svc.repo._connect() as conn:
        conn.execute(
            "UPDATE audit_schedules SET next_run_at = ? WHERE schedule_id = ?",
            ("2000-01-01T00:00:00+00:00", row["schedule_id"]),
        )
        conn.commit()

    results = svc.run_due()
    assert len(results) == 1
    assert results[0]["status"] == "queued"
    job_id = results[0]["job_id"]
    assert job_id

    job = get_job_store().get(job_id)
    assert job is not None
    assert job.payload["schedule_id"] == row["schedule_id"]
    assert job.payload["handler"] == "audit"

    updated = svc.repo.get(row["schedule_id"])
    assert updated["last_job_id"] == job_id
    # Not due again immediately
    assert svc.repo.due() == []


@responses.activate
def test_scheduled_job_finalizes_audit_id(sched_env):
    html = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/", body=html, status=200)
    responses.add(responses.GET, "https://example.com", body=html, status=200)

    app = create_app()
    with TestClient(app) as client:
        svc = ScheduleService()
        row = svc.create("https://example.com/", every_hours=24, max_pages=1)
        with svc.repo._connect() as conn:
            conn.execute(
                "UPDATE audit_schedules SET next_run_at = ? WHERE schedule_id = ?",
                ("2000-01-01T00:00:00+00:00", row["schedule_id"]),
            )
            conn.commit()

        queued = svc.run_due()
        job_id = queued[0]["job_id"]

        import time

        deadline = time.time() + 15
        final = None
        while time.time() < deadline:
            poll = client.get(f"/jobs/{job_id}")
            final = poll.json()
            if final["status"] in {"completed", "failed"}:
                break
            time.sleep(0.2)

        assert final is not None
        assert final["status"] == "completed", final
        got = svc.repo.get(row["schedule_id"])
        assert got["last_audit_id"] == final["result"]["audit_id"]
        assert got["last_error"] is None
