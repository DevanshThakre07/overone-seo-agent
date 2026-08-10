"""SQLite store for per-customer Google OAuth tokens + pending OAuth states."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from app.storage.paths import ensure_storage_dir


@dataclass
class StoredConnection:
    account_id: str
    email: str | None
    access_token: str
    refresh_token: str | None
    token_expiry: float | None
    scopes: str | None
    updated_at: float
    preferred_ga4_property_id: str | None = None


class GoogleTokenStore:
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
                CREATE TABLE IF NOT EXISTS gsc_connections (
                    account_id TEXT PRIMARY KEY,
                    email TEXT,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    token_expiry REAL,
                    scopes TEXT,
                    updated_at REAL NOT NULL,
                    preferred_ga4_property_id TEXT
                )
                """
            )
            cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(gsc_connections)").fetchall()
            }
            if "preferred_ga4_property_id" not in cols:
                conn.execute(
                    "ALTER TABLE gsc_connections "
                    "ADD COLUMN preferred_ga4_property_id TEXT"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gsc_oauth_states (
                    state TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    def save_pending_state(self, state: str, account_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO gsc_oauth_states (state, account_id, created_at) "
                "VALUES (?, ?, ?)",
                (state, account_id, time.time()),
            )

    def consume_pending_state(self, state: str, *, max_age_seconds: float = 600) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT account_id, created_at FROM gsc_oauth_states WHERE state = ?",
                (state,),
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM gsc_oauth_states WHERE state = ?", (state,))
            if time.time() - float(row["created_at"]) > max_age_seconds:
                return None
            return str(row["account_id"])

    def upsert_connection(
        self,
        *,
        account_id: str,
        access_token: str,
        refresh_token: str | None,
        expires_in: int | None = None,
        email: str | None = None,
        scopes: str | None = None,
    ) -> None:
        expiry = (time.time() + expires_in - 60) if expires_in else None
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT refresh_token, email, preferred_ga4_property_id "
                "FROM gsc_connections WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            # Google only returns refresh_token on first consent — keep the old one.
            kept_refresh = refresh_token or (
                existing["refresh_token"] if existing else None
            )
            kept_email = email or (existing["email"] if existing else None)
            kept_pref = (
                existing["preferred_ga4_property_id"] if existing else None
            )
            conn.execute(
                """
                INSERT INTO gsc_connections (
                    account_id, email, access_token, refresh_token,
                    token_expiry, scopes, updated_at, preferred_ga4_property_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    email = excluded.email,
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    token_expiry = excluded.token_expiry,
                    scopes = excluded.scopes,
                    updated_at = excluded.updated_at
                """,
                (
                    account_id,
                    kept_email,
                    access_token,
                    kept_refresh,
                    expiry,
                    scopes,
                    time.time(),
                    kept_pref,
                ),
            )

    def get_preferred_ga4_property_id(self, account_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT preferred_ga4_property_id FROM gsc_connections "
                "WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        value = row["preferred_ga4_property_id"]
        return str(value).strip() if value else None

    def set_preferred_ga4_property_id(
        self, account_id: str, property_id: str | None
    ) -> bool:
        """Set or clear preferred GA4 property. Returns False if account unknown."""
        pid = (property_id or "").strip() or None
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE gsc_connections SET preferred_ga4_property_id = ?, "
                "updated_at = ? WHERE account_id = ?",
                (pid, time.time(), account_id),
            )
            return cur.rowcount > 0

    def _row_to_connection(self, row: sqlite3.Row) -> StoredConnection:
        keys = row.keys()
        pref = None
        if "preferred_ga4_property_id" in keys:
            raw = row["preferred_ga4_property_id"]
            pref = str(raw).strip() if raw else None
        return StoredConnection(
            account_id=row["account_id"],
            email=row["email"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            token_expiry=row["token_expiry"],
            scopes=row["scopes"],
            updated_at=row["updated_at"],
            preferred_ga4_property_id=pref,
        )

    def get_connection(self, account_id: str) -> StoredConnection | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gsc_connections WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_connection(row)

    def delete_connection(self, account_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM gsc_connections WHERE account_id = ?",
                (account_id,),
            )
            return cur.rowcount > 0

    def list_connections(self) -> list[StoredConnection]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM gsc_connections ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_connection(row) for row in rows]
