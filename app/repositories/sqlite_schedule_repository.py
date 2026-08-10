"""SQLite store for recurring audit schedules."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.storage.paths import ensure_storage_dir
from app.utils.url import normalize_url


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqliteScheduleRepository:
    def __init__(self, path: str) -> None:
        self.path = ensure_storage_dir(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

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
                    created_at TEXT NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT NOT NULL,
                    last_audit_id TEXT,
                    last_error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_schedules_next "
                "ON audit_schedules(enabled, next_run_at)"
            )
            cols = {
                r[1]
                for r in conn.execute("PRAGMA table_info(audit_schedules)").fetchall()
            }
            if "last_job_id" not in cols:
                conn.execute(
                    "ALTER TABLE audit_schedules ADD COLUMN last_job_id TEXT"
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
            "created_at": now.isoformat(),
            "last_run_at": None,
            "next_run_at": next_run.isoformat(),
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        return self._public(row)

    def list_all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_schedules ORDER BY created_at DESC"
            ).fetchall()
        return [self._public(dict(r)) for r in rows]

    def get(self, schedule_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_schedules WHERE schedule_id = ?",
                (schedule_id,),
            ).fetchone()
        return self._public(dict(row)) if row else None

    def delete(self, schedule_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM audit_schedules WHERE schedule_id = ?",
                (schedule_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def set_enabled(self, schedule_id: str, enabled: bool) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE audit_schedules SET enabled = ? WHERE schedule_id = ?",
                (1 if enabled else 0, schedule_id),
            )
            conn.commit()
        return self.get(schedule_id)

    def due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        stamp = (now or _utcnow()).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_schedules
                WHERE enabled = 1 AND next_run_at <= ?
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
                SET last_run_at = ?, next_run_at = ?, last_audit_id = ?,
                    last_error = ?, last_job_id = COALESCE(?, last_job_id)
                WHERE schedule_id = ?
                """,
                (
                    now.isoformat(),
                    next_run.isoformat(),
                    audit_id,
                    error,
                    job_id,
                    schedule_id,
                ),
            )
            conn.commit()

    def mark_enqueued(self, schedule_id: str, *, job_id: str) -> None:
        """Advance next_run when a durable job is queued (avoids double-enqueue)."""
        self.mark_run(schedule_id, audit_id=None, error=None, job_id=job_id)

    def set_last_result(
        self,
        schedule_id: str,
        *,
        audit_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update result fields without moving next_run_at."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE audit_schedules
                SET last_audit_id = ?, last_error = ?
                WHERE schedule_id = ?
                """,
                (audit_id, error, schedule_id),
            )
            conn.commit()

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        pagespeed = row.get("pagespeed")
        return {
            "schedule_id": row["schedule_id"],
            "seed_url": row["seed_url"],
            "every_hours": row["every_hours"],
            "max_pages": row.get("max_pages"),
            "gsc_account_id": row.get("gsc_account_id"),
            "pagespeed": None if pagespeed is None else bool(pagespeed),
            "enabled": bool(row.get("enabled")),
            "created_at": row.get("created_at"),
            "last_run_at": row.get("last_run_at"),
            "next_run_at": row.get("next_run_at"),
            "last_audit_id": row.get("last_audit_id"),
            "last_error": row.get("last_error"),
            "last_job_id": row.get("last_job_id"),
        }
