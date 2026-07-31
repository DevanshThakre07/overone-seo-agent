from __future__ import annotations

from functools import lru_cache

from app.api.jobs import InProcessJobRunner, JobRunner
from app.config.settings import Settings, get_settings
from app.repositories.sqlite_audit_repository import SqliteAuditRepository
from app.services.memory_service import MemoryService
from app.services.report_service import ReportService


@lru_cache(maxsize=1)
def get_job_runner() -> JobRunner:
    return InProcessJobRunner(max_workers=2)


def get_app_settings() -> Settings:
    return get_settings()


def get_audit_repository() -> SqliteAuditRepository:
    settings = get_settings()
    return SqliteAuditRepository(settings.storage.path)


def get_memory_service() -> MemoryService:
    return MemoryService(get_audit_repository())


def get_report_service() -> ReportService:
    return ReportService(repository=get_audit_repository())
