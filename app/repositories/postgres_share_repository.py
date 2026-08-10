"""Postgres store for public report share tokens."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


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


class PostgresShareRepository:
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
                CREATE TABLE IF NOT EXISTS report_shares (
                    token TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL
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
                VALUES (%s, %s, %s, %s)
                """,
                (token, audit_id, now, expires),
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
                "SELECT * FROM report_shares WHERE token = %s",
                (token,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        expires = data["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        created = data["created_at"]
        if isinstance(created, datetime):
            created = created.isoformat()
        expires_out = expires.isoformat()
        return {
            "token": data["token"],
            "audit_id": data["audit_id"],
            "created_at": created,
            "expires_at": expires_out,
            "expired": expires < _utcnow(),
        }
