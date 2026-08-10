"""Postgres durable job queue."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.api.jobs import JobRecord, JobStatus


def _require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Postgres selected (SEO_DATABASE_URL set) but psycopg is not installed. "
            "Run: pip install 'seo-agent[postgres]' or pip install 'psycopg[binary]'"
        ) from exc
    return psycopg, dict_row, Jsonb


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresJobStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._init_db()

    def _connect(self):
        psycopg, dict_row, _ = _require_psycopg()
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    result_type TEXT,
                    payload JSONB NOT NULL,
                    result JSONB,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    started_at TIMESTAMPTZ,
                    finished_at TIMESTAMPTZ,
                    claimed_by TEXT,
                    claim_expires_at TIMESTAMPTZ
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_created "
                "ON jobs(status, created_at)"
            )
            conn.commit()

    def enqueue(self, *, result_type: str, payload: dict[str, Any]) -> str:
        _, _, Jsonb = _require_psycopg()
        job_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, result_type, payload, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    JobStatus.PENDING.value,
                    result_type,
                    Jsonb(payload),
                    _utcnow(),
                ),
            )
            conn.commit()
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def claim_next(
        self, *, worker_id: str, lease_seconds: int = 3600
    ) -> JobRecord | None:
        now = _utcnow()
        expires = now + timedelta(seconds=lease_seconds)
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE jobs SET
                    status = %s,
                    started_at = %s,
                    claimed_by = %s,
                    claim_expires_at = %s,
                    error = NULL
                WHERE job_id = (
                    SELECT job_id FROM jobs
                    WHERE status = %s
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
                """,
                (
                    JobStatus.RUNNING.value,
                    now,
                    worker_id,
                    expires,
                    JobStatus.PENDING.value,
                ),
            ).fetchone()
            conn.commit()
        if not row:
            return None
        return self._row_to_record(row)

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        _, _, Jsonb = _require_psycopg()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = %s,
                    result = %s,
                    error = NULL,
                    finished_at = %s,
                    claim_expires_at = NULL
                WHERE job_id = %s
                """,
                (
                    JobStatus.COMPLETED.value,
                    Jsonb(result),
                    _utcnow(),
                    job_id,
                ),
            )
            conn.commit()

    def fail(self, job_id: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = %s,
                    error = %s,
                    finished_at = %s,
                    claim_expires_at = NULL
                WHERE job_id = %s
                """,
                (
                    JobStatus.FAILED.value,
                    error[:2000],
                    _utcnow(),
                    job_id,
                ),
            )
            conn.commit()

    def reclaim_stale(self, *, older_than_seconds: int = 3600) -> int:
        cutoff = _utcnow() - timedelta(seconds=older_than_seconds)
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE jobs SET
                    status = %s,
                    claimed_by = NULL,
                    claim_expires_at = NULL,
                    started_at = NULL
                WHERE status = %s
                  AND claim_expires_at IS NOT NULL
                  AND claim_expires_at < %s
                """,
                (JobStatus.PENDING.value, JobStatus.RUNNING.value, cutoff),
            )
            conn.commit()
            return cur.rowcount

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> JobRecord:
        result = row.get("result")
        if isinstance(result, str):
            result = json.loads(result)
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        return JobRecord(
            job_id=row["job_id"],
            status=JobStatus(row["status"]),
            result_type=row.get("result_type"),
            result=result,
            error=row.get("error"),
            payload=payload,
        )
