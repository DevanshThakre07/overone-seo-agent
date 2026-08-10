"""SQLite store for public report share tokens."""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.storage.paths import ensure_storage_dir


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqliteShareRepository:
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
                CREATE TABLE IF NOT EXISTS report_shares (
                    token TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_shares_audit ON report_shares(audit_id)"
            )
            conn.commit()

    def create(self, audit_id: str, *, days_valid: int = 30) -> dict[str, Any]:
        now = _utcnow()
        days = max(1, min(int(days_valid or 30), 365))
        token = secrets.token_urlsafe(24)
        expires = now + timedelta(days=days)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO report_shares (token, audit_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, audit_id, now.isoformat(), expires.isoformat()),
            )
            conn.commit()
        return {
            "token": token,
            "audit_id": audit_id,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "share_path": f"/share/{token}",
        }

    def get(self, token: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_shares WHERE token = ?",
                (token,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        expires = datetime.fromisoformat(data["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < _utcnow():
            return {**data, "expired": True}
        return {**data, "expired": False}
