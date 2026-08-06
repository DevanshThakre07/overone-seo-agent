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


@lru_cache(maxsize=1)
def get_gsc_service():
    from app.integrations.google.service import GoogleSearchConsoleService

    return GoogleSearchConsoleService(get_settings())


@lru_cache(maxsize=1)
def get_pagespeed_service():
    from app.integrations.google.pagespeed_service import PageSpeedService

    return PageSpeedService(get_settings())


@lru_cache(maxsize=1)
def get_keyword_research_service():
    from app.integrations.dataforseo.service import KeywordResearchService

    return KeywordResearchService(get_settings())
