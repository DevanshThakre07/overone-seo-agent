"""Postgres store for recurring audit schedules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.utils.url import normalize_url


def _require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Postgres selected (SEO_DATABASE_URL set) but psycopg is not installed. "
            "Run: pip install 'seo-agent[postgres]'"
        ) from exc
    return psycopg, dict_row


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresScheduleRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._init_db()

    def _connect(self):
        psycopg, dict_row = _require_psycopg()
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    seed_url TEXT NOT NULL,
                    every_hours INTEGER NOT NULL DEFAULT 24,
                    max_pages INTEGER,
                    gsc_account_id TEXT,
                    pagespeed INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMPTZ NOT NULL,
                    last_run_at TIMESTAMPTZ,
                    next_run_at TIMESTAMPTZ NOT NULL,
                    last_audit_id TEXT,
                    last_error TEXT,
                    last_job_id TEXT
                )
                """
            )
            conn.execute(
                "ALTER TABLE audit_schedules "
                "ADD COLUMN IF NOT EXISTS last_job_id TEXT"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_schedules_next "
                "ON audit_schedules(enabled, next_run_at)"
            )
            conn.commit()

    def create(
        self,
        url: str,
        *,
        every_hours: int = 24,
        max_pages: int | None = None,
        gsc_account_id: str | None = None,
        pagespeed: bool | None = None,
    ) -> dict[str, Any]:
        now = _utcnow()
        hours = max(1, min(int(every_hours or 24), 24 * 30))
        next_run = now + timedelta(hours=hours)
        row = {
            "schedule_id": str(uuid4()),
            "seed_url": normalize_url(url),
            "every_hours": hours,
            "max_pages": max_pages,
            "gsc_account_id": gsc_account_id,
            "pagespeed": None if pagespeed is None else (1 if pagespeed else 0),
            "enabled": 1,
            "created_at": now,
            "last_run_at": None,
            "next_run_at": next_run,
            "last_audit_id": None,
            "last_error": None,
            "last_job_id": None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_schedules (
                    schedule_id, seed_url, every_hours, max_pages, gsc_account_id,
                    pagespeed, enabled, created_at, last_run_at, next_run_at,
                    last_audit_id, last_error, last_job_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    row["schedule_id"],
                    row["seed_url"],
                    row["every_hours"],
                    row["max_pages"],
                    row["gsc_account_id"],
                    row["pagespeed"],
                    row["enabled"],
                    row["created_at"],
                    row["last_run_at"],
                    row["next_run_at"],
                    row["last_audit_id"],
                    row["last_error"],
                    row["last_job_id"],
                ),
            )
            conn.commit()
        return self.get(row["schedule_id"])  # type: ignore[return-value]

    def list_all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_schedules ORDER BY created_at DESC"
            ).fetchall()
        return [self._public(dict(r)) for r in rows]

    def get(self, schedule_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_schedules WHERE schedule_id = %s",
                (schedule_id,),
            ).fetchone()
        return self._public(dict(row)) if row else None

    def delete(self, schedule_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM audit_schedules WHERE schedule_id = %s",
                (schedule_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def set_enabled(self, schedule_id: str, enabled: bool) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE audit_schedules SET enabled = %s WHERE schedule_id = %s",
                (1 if enabled else 0, schedule_id),
            )
            conn.commit()
        return self.get(schedule_id)

    def due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        stamp = now or _utcnow()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_schedules
                WHERE enabled = 1 AND next_run_at <= %s
                ORDER BY next_run_at ASC
                LIMIT 20
                """,
                (stamp,),
            ).fetchall()
        return [self._public(dict(r)) for r in rows]

    def mark_run(
        self,
        schedule_id: str,
        *,
        audit_id: str | None = None,
        error: str | None = None,
        job_id: str | None = None,
    ) -> None:
        row = self.get(schedule_id)
        if not row:
            return
        now = _utcnow()
        next_run = now + timedelta(hours=int(row["every_hours"]))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE audit_schedules
                SET last_run_at = %s, next_run_at = %s, last_audit_id = %s,
                    last_error = %s,
                    last_job_id = COALESCE(%s, last_job_id)
                WHERE schedule_id = %s
                """,
                (now, next_run, audit_id, error, job_id, schedule_id),
            )
            conn.commit()

    def mark_enqueued(self, schedule_id: str, *, job_id: str) -> None:
        self.mark_run(schedule_id, audit_id=None, error=None, job_id=job_id)

    def set_last_result(
        self,
        schedule_id: str,
        *,
        audit_id: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE audit_schedules
                SET last_audit_id = %s, last_error = %s
                WHERE schedule_id = %s
                """,
                (audit_id, error, schedule_id),
            )
            conn.commit()

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        pagespeed = row.get("pagespeed")

        def _iso(v: Any) -> Any:
            if isinstance(v, datetime):
                return v.isoformat()
            return v

        return {
            "schedule_id": row["schedule_id"],
            "seed_url": row["seed_url"],
            "every_hours": row["every_hours"],
            "max_pages": row.get("max_pages"),
            "gsc_account_id": row.get("gsc_account_id"),
            "pagespeed": None if pagespeed is None else bool(pagespeed),
            "enabled": bool(row.get("enabled")),
            "created_at": _iso(row.get("created_at")),
            "last_run_at": _iso(row.get("last_run_at")),
            "next_run_at": _iso(row.get("next_run_at")),
            "last_audit_id": row.get("last_audit_id"),
            "last_error": row.get("last_error"),
            "last_job_id": row.get("last_job_id"),
        }
