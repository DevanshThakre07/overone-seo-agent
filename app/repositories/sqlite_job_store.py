"""SQLite durable job queue (same DB file as audits by default)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.api.jobs import JobRecord, JobStatus
from app.storage.paths import ensure_storage_dir


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class SqliteJobStore:
    def __init__(self, path: str) -> None:
        self.path = ensure_storage_dir(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    result_type TEXT,
                    payload TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    claimed_by TEXT,
                    claim_expires_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_created "
                "ON jobs(status, created_at)"
            )
            conn.commit()

    def enqueue(self, *, result_type: str, payload: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        now = _iso(_utcnow())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, result_type, payload, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    JobStatus.PENDING.value,
                    result_type,
                    json.dumps(payload),
                    now,
                ),
            )
            conn.commit()
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def claim_next(
        self, *, worker_id: str, lease_seconds: int = 3600
    ) -> JobRecord | None:
        now = _utcnow()
        expires = _iso(now + timedelta(seconds=lease_seconds))
        started = _iso(now)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT job_id FROM jobs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (JobStatus.PENDING.value,),
            ).fetchone()
            if not row:
                conn.execute("COMMIT")
                return None
            job_id = row["job_id"]
            conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    started_at = ?,
                    claimed_by = ?,
                    claim_expires_at = ?,
                    error = NULL
                WHERE job_id = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    started,
                    worker_id,
                    expires,
                    job_id,
                    JobStatus.PENDING.value,
                ),
            )
            claimed = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            conn.execute("COMMIT")
        if not claimed or claimed["status"] != JobStatus.RUNNING.value:
            return None
        return self._row_to_record(claimed)

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    result = ?,
                    error = NULL,
                    finished_at = ?,
                    claim_expires_at = NULL
                WHERE job_id = ?
                """,
                (
                    JobStatus.COMPLETED.value,
                    json.dumps(result),
                    _iso(_utcnow()),
                    job_id,
                ),
            )
            conn.commit()

    def fail(self, job_id: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    error = ?,
                    finished_at = ?,
                    claim_expires_at = NULL
                WHERE job_id = ?
                """,
                (
                    JobStatus.FAILED.value,
                    error[:2000],
                    _iso(_utcnow()),
                    job_id,
                ),
            )
            conn.commit()

    def reclaim_stale(self, *, older_than_seconds: int = 3600) -> int:
        cutoff = _iso(_utcnow() - timedelta(seconds=older_than_seconds))
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE jobs SET
                    status = ?,
                    claimed_by = NULL,
                    claim_expires_at = NULL,
                    started_at = NULL
                WHERE status = ?
                  AND claim_expires_at IS NOT NULL
                  AND claim_expires_at < ?
                """,
                (JobStatus.PENDING.value, JobStatus.RUNNING.value, cutoff),
            )
            conn.commit()
            return cur.rowcount

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        result = None
        if row["result"]:
            result = json.loads(row["result"])
        payload = json.loads(row["payload"]) if row["payload"] else {}
        return JobRecord(
            job_id=row["job_id"],
            status=JobStatus(row["status"]),
            result_type=row["result_type"],
            result=result,
            error=row["error"],
            payload=payload,
        )
