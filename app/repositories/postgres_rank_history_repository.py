"""Postgres store for keyword rank snapshots over time."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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


class PostgresRankHistoryRepository:
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
                CREATE TABLE IF NOT EXISTS rank_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    seed_url TEXT NOT NULL,
                    target_domain TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    checked_at TIMESTAMPTZ NOT NULL,
                    found INTEGER NOT NULL DEFAULT 0,
                    position INTEGER,
                    rank_absolute INTEGER,
                    result_url TEXT,
                    title TEXT,
                    device TEXT,
                    provider TEXT,
                    audit_id TEXT,
                    source TEXT,
                    payload JSONB
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rank_domain_kw "
                "ON rank_snapshots(target_domain, keyword, checked_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rank_seed "
                "ON rank_snapshots(seed_url, checked_at DESC)"
            )
            conn.commit()

    def record(self, row: dict[str, Any]) -> dict[str, Any]:
        snapshot_id = row.get("snapshot_id") or str(uuid4())
        checked_at = row.get("checked_at") or _utcnow()
        if isinstance(checked_at, str):
            try:
                checked_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            except ValueError:
                checked_at = _utcnow()
        seed = normalize_url(str(row.get("seed_url") or row.get("target_domain") or ""))
        payload = row.get("payload")
        if isinstance(payload, str) and payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {"raw": payload}
        out = {
            "snapshot_id": snapshot_id,
            "seed_url": seed,
            "target_domain": str(row.get("target_domain") or ""),
            "keyword": str(row.get("keyword") or "").strip().lower(),
            "checked_at": checked_at,
            "found": 1 if row.get("found") else 0,
            "position": row.get("position"),
            "rank_absolute": row.get("rank_absolute"),
            "result_url": row.get("result_url"),
            "title": row.get("title"),
            "device": row.get("device"),
            "provider": row.get("provider"),
            "audit_id": row.get("audit_id"),
            "source": row.get("source") or "rank_check",
            "payload": payload,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rank_snapshots (
                    snapshot_id, seed_url, target_domain, keyword, checked_at,
                    found, position, rank_absolute, result_url, title, device,
                    provider, audit_id, source, payload
                ) VALUES (
                    %(snapshot_id)s, %(seed_url)s, %(target_domain)s, %(keyword)s,
                    %(checked_at)s, %(found)s, %(position)s, %(rank_absolute)s,
                    %(result_url)s, %(title)s, %(device)s, %(provider)s,
                    %(audit_id)s, %(source)s, %(payload)s
                )
                """,
                {**out, "payload": json.dumps(payload) if payload is not None else None},
            )
            conn.commit()
        return self._public(out)

    def list_history(
        self,
        *,
        seed_url: str | None = None,
        target_domain: str | None = None,
        keyword: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if seed_url:
            clauses.append("seed_url = %(seed_url)s")
            params["seed_url"] = normalize_url(seed_url)
        if target_domain:
            clauses.append("target_domain = %(target_domain)s")
            params["target_domain"] = str(target_domain).lower().lstrip("www.")
        if keyword:
            clauses.append("keyword = %(keyword)s")
            params["keyword"] = str(keyword).strip().lower()
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT * FROM rank_snapshots"
            f"{where} ORDER BY checked_at DESC LIMIT %(limit)s"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._public(dict(r)) for r in rows]

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        checked = row.get("checked_at")
        if hasattr(checked, "isoformat"):
            checked = checked.isoformat()
        payload = row.get("payload")
        if isinstance(payload, str) and payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        return {
            "snapshot_id": row.get("snapshot_id"),
            "seed_url": row.get("seed_url"),
            "target_domain": row.get("target_domain"),
            "keyword": row.get("keyword"),
            "checked_at": checked,
            "found": bool(row.get("found")),
            "position": row.get("position"),
            "rank_absolute": row.get("rank_absolute"),
            "result_url": row.get("result_url"),
            "title": row.get("title"),
            "device": row.get("device"),
            "provider": row.get("provider"),
            "audit_id": row.get("audit_id"),
            "source": row.get("source"),
            "payload": payload,
        }
