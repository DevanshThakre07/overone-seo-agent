"""Configuration loaded from YAML defaults with environment overrides."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.yaml"


class CrawlSettings(BaseModel):
    max_pages: int = 50
    max_depth: int = 3
    timeout_seconds: float = 15.0
    concurrency: int = 5
    delay_seconds: float = 0.25
    user_agent: str = "SEO-Agent/0.1"
    respect_robots: bool = True
    max_redirects: int = 5
    same_host_only: bool = True
    check_external_links: bool = True
    max_external_link_checks: int = 100


class PlaywrightSettings(BaseModel):
    enabled: bool = False
    timeout_ms: int = 30_000
    wait_until: str = "networkidle"


class ScoringWeights(BaseModel):
    critical: int = 8
    warning: int = 3
    info: int = 1


class ScoringSettings(BaseModel):
    base_score: int = 100
    weights: ScoringWeights = Field(default_factory=ScoringWeights)


class AnalyzerSettings(BaseModel):
    page_size_threshold_bytes: int = 3_145_728
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)


class StorageSettings(BaseModel):
    backend: str = "sqlite"
    path: str = "data/audits.db"


class LLMSettings(BaseModel):
    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    timeout_seconds: float = 60.0
    optimize_max_pages: int = 5


class LoggingSettings(BaseModel):
    level: str = "INFO"
    json_logs: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str | None = Field(default=None, validation_alias="LOG_LEVEL")
    log_json: bool | None = Field(default=None, validation_alias="LOG_JSON")

    seo_crawl_max_pages: int | None = Field(default=None, validation_alias="SEO_CRAWL_MAX_PAGES")
    seo_crawl_max_depth: int | None = Field(default=None, validation_alias="SEO_CRAWL_MAX_DEPTH")
    seo_crawl_timeout: float | None = Field(default=None, validation_alias="SEO_CRAWL_TIMEOUT")
    seo_crawl_concurrency: int | None = Field(default=None, validation_alias="SEO_CRAWL_CONCURRENCY")
    seo_crawl_user_agent: str | None = Field(default=None, validation_alias="SEO_CRAWL_USER_AGENT")

    seo_storage_backend: str | None = Field(default=None, validation_alias="SEO_STORAGE_BACKEND")
    seo_storage_path: str | None = Field(default=None, validation_alias="SEO_STORAGE_PATH")

    seo_playwright_enabled: bool | None = Field(
        default=None, validation_alias="SEO_PLAYWRIGHT_ENABLED"
    )

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_model: str | None = Field(default=None, validation_alias="LLM_MODEL")

    crawl: CrawlSettings = Field(default_factory=CrawlSettings)
    playwright: PlaywrightSettings = Field(default_factory=PlaywrightSettings)
    analyzer: AnalyzerSettings = Field(default_factory=AnalyzerSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> Settings:
        config_path = path or DEFAULT_CONFIG_PATH
        raw: dict[str, Any] = {}
        if config_path.exists():
            with config_path.open(encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}

        settings = cls(
            crawl=CrawlSettings(**(raw.get("crawl") or {})),
            playwright=PlaywrightSettings(**(raw.get("playwright") or {})),
            analyzer=AnalyzerSettings(**(raw.get("analyzer") or {})),
            storage=StorageSettings(**(raw.get("storage") or {})),
            llm=LLMSettings(**(raw.get("llm") or {})),
            logging=LoggingSettings(**(raw.get("logging") or {})),
        )
        return settings.apply_env_overrides()

    def apply_env_overrides(self) -> Settings:
        if self.log_level is not None:
            self.logging.level = self.log_level
        if self.log_json is not None:
            self.logging.json_logs = self.log_json

        if self.seo_crawl_max_pages is not None:
            self.crawl.max_pages = self.seo_crawl_max_pages
        if self.seo_crawl_max_depth is not None:
            self.crawl.max_depth = self.seo_crawl_max_depth
        if self.seo_crawl_timeout is not None:
            self.crawl.timeout_seconds = self.seo_crawl_timeout
        if self.seo_crawl_concurrency is not None:
            self.crawl.concurrency = self.seo_crawl_concurrency
        if self.seo_crawl_user_agent is not None:
            self.crawl.user_agent = self.seo_crawl_user_agent

        if self.seo_storage_backend is not None:
            self.storage.backend = self.seo_storage_backend
        if self.seo_storage_path is not None:
            self.storage.path = self.seo_storage_path

        if self.seo_playwright_enabled is not None:
            self.playwright.enabled = self.seo_playwright_enabled

        if self.llm_base_url is not None:
            self.llm.base_url = self.llm_base_url
        if self.llm_model is not None:
            self.llm.model = self.llm_model

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_yaml()
