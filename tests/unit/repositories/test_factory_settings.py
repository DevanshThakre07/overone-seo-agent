"""Storage factory picks Postgres only when DATABASE_URL is set."""

from __future__ import annotations

from app.config import settings as settings_module
from app.repositories.factory import get_audit_repository, resolve_database_url, use_postgres
from app.repositories.sqlite_audit_repository import SqliteAuditRepository


def test_sqlite_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SEO_STORAGE_PATH", str(tmp_path / "a.db"))
    monkeypatch.delenv("SEO_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings_module.get_settings.cache_clear()

    s = settings_module.get_settings()
    assert resolve_database_url(s) is None
    assert use_postgres(s) is False
    repo = get_audit_repository(s)
    assert isinstance(repo, SqliteAuditRepository)

    settings_module.get_settings.cache_clear()


def test_database_url_selects_postgres_backend(monkeypatch):
    monkeypatch.setenv(
        "SEO_DATABASE_URL",
        "postgresql://user:pass@localhost:5432/seo_agent",
    )
    settings_module.get_settings.cache_clear()
    s = settings_module.get_settings()
    assert s.storage.backend == "postgres"
    assert "postgresql://" in (s.storage.database_url or "")
    settings_module.get_settings.cache_clear()
