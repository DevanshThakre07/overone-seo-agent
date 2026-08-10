from __future__ import annotations

from functools import lru_cache

from app.api.jobs import DurableJobRunner, JobRunner
from app.config.settings import Settings, get_settings
from app.repositories.base import AuditRepository
from app.repositories.factory import get_audit_repository as factory_audit_repository
from app.repositories.factory import get_job_store
from app.services.memory_service import MemoryService
from app.services.report_service import ReportService


@lru_cache(maxsize=1)
def get_job_runner() -> JobRunner:
    settings = get_settings()
    store = get_job_store(settings)
    return DurableJobRunner(
        store,
        max_workers=settings.storage.job_workers,
    )


def get_app_settings() -> Settings:
    return get_settings()


def get_audit_repository() -> AuditRepository:
    return factory_audit_repository()


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


@lru_cache(maxsize=1)
def get_competitive_seo_service():
    from app.integrations.dataforseo.competitive import CompetitiveSeoService

    return CompetitiveSeoService(get_settings())


@lru_cache(maxsize=1)
def get_ga4_service():
    from app.integrations.google.ga4_service import Ga4Service

    return Ga4Service(get_settings())
