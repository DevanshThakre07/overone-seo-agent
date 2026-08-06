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
    # Cost of a page-level issue present on every crawled page, per unit of
    # severity weight. Raise for a stricter grader, lower for a lenient one.
    prevalence_scale: float = 3.0
    # Ceiling on the combined page-level penalty, so no volume of issues can
    # collapse the score to a meaningless 0.
    max_page_level_penalty: float = 60.0
    # Minimum pages before prevalence weighting is statistically meaningful.
    # Below this, severity weights are charged flat per affected page.
    min_pages_for_prevalence: int = 5


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


class GoogleSearchConsoleSettings(BaseModel):
    """OAuth + Search Console for per-client Google connections.

    The product owner keeps one OAuth client. Each customer connects their own
    Google account (and verified Search Console properties) via Connect Google.
    """

    enabled: bool = True
    client_secrets_file: str = "secrets/google-oauth-client.json"
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str = "http://localhost:8000/auth/callback"
    token_db_path: str = "data/gsc_tokens.db"
    scopes: list[str] = Field(
        default_factory=lambda: [
            "https://www.googleapis.com/auth/webmasters.readonly",
            "openid",
            "email",
        ]
    )


class PageSpeedSettings(BaseModel):
    """Google PageSpeed Insights (Core Web Vitals / Lighthouse).

    Uses a simple API key — no OAuth. Runs on the audit seed URL only by
    default (PSI is slow and rate-limited).
    """

    enabled: bool = True
    api_key: str | None = None
    # mobile | desktop | both
    strategy: str = "mobile"
    timeout_seconds: float = 90.0
    # Lab score 0–100 below this → warning
    performance_score_warn: int = 50
    # Core Web Vitals thresholds (lab), aligned with Google "good" guidance
    lcp_good_ms: float = 2500.0
    cls_good: float = 0.1
    inp_good_ms: float = 200.0


class KeywordSettings(BaseModel):
    """Paid keyword research (volume / CPC / competition + Labs).

    Keywords Data = volume/CPC. Labs = difficulty + related ideas.
    """

    enabled: bool = True
    provider: str | None = None  # dataforseo | semrush | ahrefs | google_ads
    login: str | None = None
    password: str | None = None
    api_key: str | None = None  # for semrush/ahrefs later
    # Google Ads / Labs location + language
    location_code: int = 2840  # United States
    language_code: str = "en"
    timeout_seconds: float = 60.0
    max_keywords_per_request: int = 100
    # DataForSEO Labs
    labs_enabled: bool = True
    related_depth: int = 1  # 0–4; 1 ≈ up to ~8 related ideas
    related_limit: int = 10
    include_related_in_research: bool = True


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

    gsc_client_secrets_file: str | None = Field(
        default=None, validation_alias="GSC_CLIENT_SECRETS_FILE"
    )
    gsc_client_id: str | None = Field(default=None, validation_alias="GSC_CLIENT_ID")
    gsc_client_secret: str | None = Field(default=None, validation_alias="GSC_CLIENT_SECRET")
    gsc_redirect_uri: str | None = Field(default=None, validation_alias="GSC_REDIRECT_URI")
    gsc_token_db_path: str | None = Field(default=None, validation_alias="GSC_TOKEN_DB_PATH")

    google_pagespeed_api_key: str | None = Field(
        default=None, validation_alias="GOOGLE_PAGESPEED_API_KEY"
    )
    pagespeed_strategy: str | None = Field(
        default=None, validation_alias="PAGESPEED_STRATEGY"
    )

    keyword_api_provider: str | None = Field(
        default=None, validation_alias="KEYWORD_API_PROVIDER"
    )
    keyword_api_login: str | None = Field(
        default=None, validation_alias="KEYWORD_API_LOGIN"
    )
    keyword_api_password: str | None = Field(
        default=None, validation_alias="KEYWORD_API_PASSWORD"
    )
    keyword_api_key: str | None = Field(
        default=None, validation_alias="KEYWORD_API_KEY"
    )
    keyword_location_code: int | None = Field(
        default=None, validation_alias="KEYWORD_LOCATION_CODE"
    )
    keyword_language_code: str | None = Field(
        default=None, validation_alias="KEYWORD_LANGUAGE_CODE"
    )
    keyword_labs_enabled: bool | None = Field(
        default=None, validation_alias="KEYWORD_LABS_ENABLED"
    )
    keyword_related_depth: int | None = Field(
        default=None, validation_alias="KEYWORD_RELATED_DEPTH"
    )
    keyword_related_limit: int | None = Field(
        default=None, validation_alias="KEYWORD_RELATED_LIMIT"
    )
    keyword_include_related: bool | None = Field(
        default=None, validation_alias="KEYWORD_INCLUDE_RELATED"
    )

    crawl: CrawlSettings = Field(default_factory=CrawlSettings)
    playwright: PlaywrightSettings = Field(default_factory=PlaywrightSettings)
    analyzer: AnalyzerSettings = Field(default_factory=AnalyzerSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    gsc: GoogleSearchConsoleSettings = Field(default_factory=GoogleSearchConsoleSettings)
    pagespeed: PageSpeedSettings = Field(default_factory=PageSpeedSettings)
    keywords: KeywordSettings = Field(default_factory=KeywordSettings)

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
            gsc=GoogleSearchConsoleSettings(**(raw.get("gsc") or {})),
            pagespeed=PageSpeedSettings(**(raw.get("pagespeed") or {})),
            keywords=KeywordSettings(**(raw.get("keywords") or {})),
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

        if self.gsc_client_secrets_file is not None:
            self.gsc.client_secrets_file = self.gsc_client_secrets_file
        if self.gsc_client_id is not None:
            self.gsc.client_id = self.gsc_client_id
        if self.gsc_client_secret is not None:
            self.gsc.client_secret = self.gsc_client_secret
        if self.gsc_redirect_uri is not None:
            self.gsc.redirect_uri = self.gsc_redirect_uri
        if self.gsc_token_db_path is not None:
            self.gsc.token_db_path = self.gsc_token_db_path

        if self.google_pagespeed_api_key is not None:
            self.pagespeed.api_key = self.google_pagespeed_api_key
        if self.pagespeed_strategy is not None:
            self.pagespeed.strategy = self.pagespeed_strategy

        if self.keyword_api_provider is not None:
            self.keywords.provider = (
                self.keyword_api_provider.strip().lower() or None
            )
        if self.keyword_api_login is not None:
            self.keywords.login = self.keyword_api_login.strip() or None
        if self.keyword_api_password is not None:
            self.keywords.password = self.keyword_api_password.strip() or None
        if self.keyword_api_key is not None:
            self.keywords.api_key = self.keyword_api_key.strip() or None
        if self.keyword_location_code is not None:
            self.keywords.location_code = self.keyword_location_code
        if self.keyword_language_code is not None:
            self.keywords.language_code = self.keyword_language_code
        if self.keyword_labs_enabled is not None:
            self.keywords.labs_enabled = self.keyword_labs_enabled
        if self.keyword_related_depth is not None:
            self.keywords.related_depth = self.keyword_related_depth
        if self.keyword_related_limit is not None:
            self.keywords.related_limit = self.keyword_related_limit
        if self.keyword_include_related is not None:
            self.keywords.include_related_in_research = self.keyword_include_related

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_yaml()
