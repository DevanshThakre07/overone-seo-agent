"""SQLite durable job store — enqueue / claim / complete / reclaim."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.jobs import JobStatus
from app.repositories.sqlite_job_store import SqliteJobStore


def test_enqueue_claim_complete(tmp_path):
    store = SqliteJobStore(str(tmp_path / "jobs.db"))
    job_id = store.enqueue(
        result_type="audit",
        payload={"handler": "audit", "request": {"url": "https://example.com/"}},
    )
    pending = store.get(job_id)
    assert pending is not None
    assert pending.status == JobStatus.PENDING
    assert pending.payload["handler"] == "audit"

    claimed = store.claim_next(worker_id="w1", lease_seconds=60)
    assert claimed is not None
    assert claimed.job_id == job_id
    assert claimed.status == JobStatus.RUNNING

    assert store.claim_next(worker_id="w2") is None

    store.complete(job_id, {"audit_id": "a1", "score": 90.0, "status": "completed"})
    done = store.get(job_id)
    assert done is not None
    assert done.status == JobStatus.COMPLETED
    assert done.result["audit_id"] == "a1"


def test_fail_and_reclaim_stale(tmp_path):
    store = SqliteJobStore(str(tmp_path / "jobs.db"))
    job_id = store.enqueue(result_type="audit", payload={"handler": "audit", "request": {}})
    claimed = store.claim_next(worker_id="w1", lease_seconds=1)
    assert claimed is not None

    # Force expired lease
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with store._connect() as conn:
        conn.execute(
            "UPDATE jobs SET claim_expires_at = ? WHERE job_id = ?",
            (past, job_id),
        )
        conn.commit()

    n = store.reclaim_stale(older_than_seconds=60)
    assert n == 1
    row = store.get(job_id)
    assert row is not None
    assert row.status == JobStatus.PENDING

    again = store.claim_next(worker_id="w2")
    assert again is not None
    store.fail(again.job_id, "boom")
    failed = store.get(again.job_id)
    assert failed is not None
    assert failed.status == JobStatus.FAILED
    assert failed.error == "boom"
