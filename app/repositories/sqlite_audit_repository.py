"""SQLite implementation of AuditRepository — SQL stays here only."""

from __future__ import annotations

import sqlite3

from app.models.audit import SiteAudit
from app.storage.paths import ensure_storage_dir
from app.utils.url import normalize_url


class SqliteAuditRepository:
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
                CREATE TABLE IF NOT EXISTS audits (
                    audit_id TEXT PRIMARY KEY,
                    seed_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    score REAL NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audits_seed_url ON audits(seed_url)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audits_seed_created "
                "ON audits(seed_url, created_at DESC)"
            )
            conn.commit()

    def save(self, audit: SiteAudit) -> SiteAudit:
        seed = normalize_url(audit.seed_url)
        # Keep stored model consistent with lookup key
        if audit.seed_url != seed:
            audit.seed_url = seed
        payload = audit.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO audits (audit_id, seed_url, created_at, score, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    audit.audit_id,
                    seed,
                    audit.created_at.isoformat(),
                    audit.score,
                    payload,
                ),
            )
            conn.commit()
        return audit

    def get(self, audit_id: str) -> SiteAudit | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM audits WHERE audit_id = ?", (audit_id,)
            ).fetchone()
        if not row:
            return None
        return SiteAudit.model_validate_json(row["payload"])

    def list_by_url(self, url: str, *, limit: int = 20) -> list[SiteAudit]:
        seed = normalize_url(url)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM audits
                WHERE seed_url = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (seed, limit),
            ).fetchall()
        return [SiteAudit.model_validate_json(r["payload"]) for r in rows]

    def latest(self, url: str) -> SiteAudit | None:
        items = self.list_by_url(url, limit=1)
        return items[0] if items else None

    def previous(
        self, url: str, *, before_audit_id: str | None = None
    ) -> SiteAudit | None:
        """Return the most recent audit for url, optionally excluding one audit id."""
        seed = normalize_url(url)
        with self._connect() as conn:
            if before_audit_id:
                row = conn.execute(
                    """
                    SELECT payload FROM audits
                    WHERE seed_url = ? AND audit_id != ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (seed, before_audit_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT payload FROM audits
                    WHERE seed_url = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (seed,),
                ).fetchone()
        if not row:
            return None
        return SiteAudit.model_validate_json(row["payload"])

    def delete(self, audit_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM audits WHERE audit_id = ?", (audit_id,))
            conn.commit()
            return cur.rowcount > 0
