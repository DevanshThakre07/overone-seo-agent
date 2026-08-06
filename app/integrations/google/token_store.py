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
                    updated_at REAL NOT NULL
                )
                """
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
                "SELECT refresh_token, email FROM gsc_connections WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            # Google only returns refresh_token on first consent — keep the old one.
            kept_refresh = refresh_token or (
                existing["refresh_token"] if existing else None
            )
            kept_email = email or (existing["email"] if existing else None)
            conn.execute(
                """
                INSERT INTO gsc_connections (
                    account_id, email, access_token, refresh_token,
                    token_expiry, scopes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

    def get_connection(self, account_id: str) -> StoredConnection | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gsc_connections WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredConnection(
            account_id=row["account_id"],
            email=row["email"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            token_expiry=row["token_expiry"],
            scopes=row["scopes"],
            updated_at=row["updated_at"],
        )

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
        return [
            StoredConnection(
                account_id=row["account_id"],
                email=row["email"],
                access_token=row["access_token"],
                refresh_token=row["refresh_token"],
                token_expiry=row["token_expiry"],
                scopes=row["scopes"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
