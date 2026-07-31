from __future__ import annotations

from app.analyzers.base import AnalysisContext, BaseAnalyzer
from app.analyzers.canonical_analyzer import CanonicalAnalyzer
from app.analyzers.headings_analyzer import HeadingsAnalyzer
from app.analyzers.image_alt_analyzer import ImageAltAnalyzer
from app.analyzers.links_analyzer import LinksAnalyzer
from app.analyzers.meta_description_analyzer import MetaDescriptionAnalyzer
from app.analyzers.page_size_analyzer import PageSizeAnalyzer
from app.analyzers.robots_analyzer import RobotsAnalyzer
from app.analyzers.schema_analyzer import SchemaAnalyzer
from app.analyzers.sitemap_analyzer import SitemapAnalyzer
from app.analyzers.title_analyzer import TitleAnalyzer
from app.logging import get_logger, log_event
from app.models.issues import AnalyzerResult, Issue, Severity

logger = get_logger(__name__)


class AnalyzerRegistry:
    def __init__(self) -> None:
        self._analyzers: list[BaseAnalyzer] = []

    def register(self, analyzer: BaseAnalyzer) -> None:
        self._analyzers.append(analyzer)

    def list_analyzers(self) -> list[str]:
        return [a.name for a in self._analyzers]

    def run_all(self, context: AnalysisContext) -> list[AnalyzerResult]:
        results: list[AnalyzerResult] = []
        for analyzer in self._analyzers:
            try:
                result = analyzer.analyze(context)
                results.append(result)
            except Exception as exc:  # noqa: BLE001 — isolate plugin failures
                log_event(
                    logger,
                    "warning",
                    analyzer=analyzer.name,
                    error=str(exc),
                    message="analyzer_failed",
                )
                results.append(
                    AnalyzerResult(
                        analyzer=analyzer.name,
                        issues=[
                            Issue(
                                code="analyzer_error",
                                severity=Severity.WARNING,
                                message=f"Analyzer '{analyzer.name}' failed: {exc}",
                            )
                        ],
                        error=str(exc),
                    )
                )
        return results


def build_default_registry() -> AnalyzerRegistry:
    registry = AnalyzerRegistry()
    for analyzer in (
        TitleAnalyzer(),
        MetaDescriptionAnalyzer(),
        HeadingsAnalyzer(),
        ImageAltAnalyzer(),
        LinksAnalyzer(),
        CanonicalAnalyzer(),
        RobotsAnalyzer(),
        PageSizeAnalyzer(),
        SitemapAnalyzer(),
        SchemaAnalyzer(),
    ):
        registry.register(analyzer)
    return registry
