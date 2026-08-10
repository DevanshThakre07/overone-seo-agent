"""Storage factory — Postgres when DATABASE_URL set, else SQLite."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.config.settings import Settings, get_settings
from app.repositories.base import AuditRepository


def resolve_database_url(settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    url = (s.storage.database_url or "").strip()
    return url or None


def use_postgres(settings: Settings | None = None) -> bool:
    return bool(resolve_database_url(settings))


def get_audit_repository(settings: Settings | None = None) -> AuditRepository:
    s = settings or get_settings()
    url = resolve_database_url(s)
    if url:
        from app.repositories.postgres_audit_repository import PostgresAuditRepository

        return PostgresAuditRepository(url)
    from app.repositories.sqlite_audit_repository import SqliteAuditRepository

    return SqliteAuditRepository(s.storage.path)


def get_job_store(settings: Settings | None = None):
    from app.repositories.job_store import JobStore

    s = settings or get_settings()
    url = resolve_database_url(s)
    store: JobStore
    if url:
        from app.repositories.postgres_job_store import PostgresJobStore

        store = PostgresJobStore(url)
    else:
        from app.repositories.sqlite_job_store import SqliteJobStore

        store = SqliteJobStore(s.storage.path)
    return store


def get_schedule_repository(settings: Settings | None = None) -> Any:
    s = settings or get_settings()
    url = resolve_database_url(s)
    if url:
        from app.repositories.postgres_schedule_repository import (
            PostgresScheduleRepository,
        )

        return PostgresScheduleRepository(url)
    from app.repositories.sqlite_schedule_repository import SqliteScheduleRepository

    return SqliteScheduleRepository(s.storage.path)


def get_share_repository(settings: Settings | None = None) -> Any:
    s = settings or get_settings()
    url = resolve_database_url(s)
    if url:
        from app.repositories.postgres_share_repository import PostgresShareRepository

        return PostgresShareRepository(url)
    from app.repositories.sqlite_share_repository import SqliteShareRepository

    return SqliteShareRepository(s.storage.path)


def get_rank_history_repository(settings: Settings | None = None) -> Any:
    s = settings or get_settings()
    url = resolve_database_url(s)
    if url:
        from app.repositories.postgres_rank_history_repository import (
            PostgresRankHistoryRepository,
        )

        return PostgresRankHistoryRepository(url)
    from app.repositories.sqlite_rank_history_repository import (
        SqliteRankHistoryRepository,
    )

    return SqliteRankHistoryRepository(s.storage.path)


@lru_cache(maxsize=1)
def cached_audit_repository() -> AuditRepository:
    return get_audit_repository()


@lru_cache(maxsize=1)
def cached_job_store():
    return get_job_store()
