from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.config.settings import AnalyzerSettings
from app.models.crawl import CrawlResult, CrawlStats
from app.models.issues import AnalyzerResult
from app.models.page import PageExtraction


class AnalysisContext(BaseModel):
    seed_url: str
    pages: list[PageExtraction]
    crawl_results: list[CrawlResult] = Field(default_factory=list)
    crawl_stats: CrawlStats
    config: AnalyzerSettings


@runtime_checkable
class BaseAnalyzer(Protocol):
    name: str

    def analyze(self, context: AnalysisContext) -> AnalyzerResult: ...
