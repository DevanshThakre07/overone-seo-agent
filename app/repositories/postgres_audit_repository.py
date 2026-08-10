"""Postgres implementation of AuditRepository (optional Phase 4A backend)."""

from __future__ import annotations

import json
from typing import Any

from app.models.audit import SiteAudit
from app.utils.url import normalize_url


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


class PostgresAuditRepository:
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
                CREATE TABLE IF NOT EXISTS audits (
                    audit_id TEXT PRIMARY KEY,
                    seed_url TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    score DOUBLE PRECISION NOT NULL,
                    payload JSONB NOT NULL
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
        _, _, Jsonb = _require_psycopg()
        seed = normalize_url(audit.seed_url)
        if audit.seed_url != seed:
            audit.seed_url = seed
        payload = audit.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audits (audit_id, seed_url, created_at, score, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (audit_id) DO UPDATE SET
                    seed_url = EXCLUDED.seed_url,
                    created_at = EXCLUDED.created_at,
                    score = EXCLUDED.score,
                    payload = EXCLUDED.payload
                """,
                (
                    audit.audit_id,
                    seed,
                    audit.created_at.isoformat(),
                    audit.score,
                    Jsonb(payload),
                ),
            )
            conn.commit()
        return audit

    def get(self, audit_id: str) -> SiteAudit | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM audits WHERE audit_id = %s",
                (audit_id,),
            ).fetchone()
        if not row:
            return None
        return self._to_audit(row["payload"])

    def list_by_url(self, url: str, *, limit: int = 20) -> list[SiteAudit]:
        seed = normalize_url(url)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM audits
                WHERE seed_url = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (seed, limit),
            ).fetchall()
        return [self._to_audit(r["payload"]) for r in rows]

    def latest(self, url: str) -> SiteAudit | None:
        items = self.list_by_url(url, limit=1)
        return items[0] if items else None

    def previous(
        self, url: str, *, before_audit_id: str | None = None
    ) -> SiteAudit | None:
        seed = normalize_url(url)
        with self._connect() as conn:
            if before_audit_id:
                row = conn.execute(
                    """
                    SELECT payload FROM audits
                    WHERE seed_url = %s AND audit_id != %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (seed, before_audit_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT payload FROM audits
                    WHERE seed_url = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (seed,),
                ).fetchone()
        if not row:
            return None
        return self._to_audit(row["payload"])

    def delete(self, audit_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM audits WHERE audit_id = %s",
                (audit_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def _to_audit(payload: Any) -> SiteAudit:
        if isinstance(payload, str):
            return SiteAudit.model_validate_json(payload)
        if isinstance(payload, dict):
            return SiteAudit.model_validate(payload)
        # memoryview / bytes from some drivers
        return SiteAudit.model_validate_json(
            payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload)
        )
