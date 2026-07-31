from __future__ import annotations

import logging
from copy import deepcopy

from app.analyzers.base import AnalysisContext
from app.analyzers.metrics import build_structured_seo_metrics
from app.analyzers.registry import AnalyzerRegistry, build_default_registry
from app.analyzers.scorer import aggregate_issues, compute_score, severity_counts
from app.config.settings import Settings, get_settings
from app.extractor.html_extractor import HtmlExtractor
from app.logging import get_logger, log_event
from app.models.audit import AuditOptions, SiteAudit
from app.repositories.base import AuditRepository
from app.services.crawler_service import CrawlerService
from app.services.memory_service import MemoryService
from app.services.optimizer_service import OptimizerService
from app.utils.url import normalize_url

logger = get_logger(__name__)


class SeoService:
    def __init__(
        self,
        settings: Settings | None = None,
        crawler_service: CrawlerService | None = None,
        registry: AnalyzerRegistry | None = None,
        extractor: HtmlExtractor | None = None,
        repository: AuditRepository | None = None,
        optimizer_service: OptimizerService | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.crawler_service = crawler_service or CrawlerService(self.settings)
        self.registry = registry or build_default_registry()
        self.extractor = extractor or HtmlExtractor()
        self.repository = repository
        self.optimizer_service = optimizer_service
        self.memory_service = memory_service
        if self.memory_service is None and self.repository is not None:
            self.memory_service = MemoryService(self.repository)

    def run_audit(self, url: str, options: AuditOptions | None = None) -> SiteAudit:
        options = options or AuditOptions()
        settings = self._apply_options(options)
        should_persist = options.save or options.compare

        previous = None
        if options.compare and self.memory_service is not None:
            previous = self.memory_service.latest(url)

        try:
            crawl_results, stats = self.crawler_service.crawl(url)
            pages = self.extractor.extract_many(crawl_results, stats.seed_url)

            context = AnalysisContext(
                seed_url=stats.seed_url,
                pages=pages,
                crawl_results=crawl_results,
                crawl_stats=stats,
                config=settings.analyzer,
            )
            analyzer_results = self.registry.run_all(context)
            issues = aggregate_issues(analyzer_results)
            score = compute_score(issues, settings.analyzer.scoring)
            counts = severity_counts(issues)

            log_event(
                logger,
                "pages_analyzed",
                url=stats.seed_url,
                pages=len(pages),
                analyzers=len(analyzer_results),
            )
            log_event(
                logger,
                "issues_detected",
                url=stats.seed_url,
                **counts,
                total=len(issues),
            )

            seo_metrics = build_structured_seo_metrics(pages, analyzer_results)
            audit = SiteAudit(
                seed_url=normalize_url(stats.seed_url),
                score=score,
                pages=pages,
                issues=issues,
                analyzer_results=analyzer_results,
                stats=stats,
                summary={
                    "pages": len(pages),
                    "issues": len(issues),
                    "severity": counts,
                    "analyzers_run": self.registry.list_analyzers(),
                    # Complete structured SEO JSON for reports / Hermes / LLM
                    "seo_metrics": seo_metrics,
                },
            )

            if options.optimize:
                optimizer = self.optimizer_service or OptimizerService(settings)
                audit.optimization = optimizer.optimize_audit(
                    audit,
                    target_keywords=options.target_keywords or None,
                    max_pages=options.optimize_max_pages
                    or settings.llm.optimize_max_pages,
                )
                audit.summary["optimization_status"] = audit.optimization.status

            if options.compare and self.memory_service is not None:
                audit.diff = self.memory_service.compare(audit, previous=previous)
                audit.summary["compare"] = {
                    "has_baseline": audit.diff.has_baseline,
                    "score_delta": audit.diff.score_delta,
                    "new_issues": len(audit.diff.new_issues),
                    "resolved_issues": len(audit.diff.resolved_issues),
                }

            if should_persist and self.memory_service is not None:
                self.memory_service.save(audit)
            elif should_persist and self.repository is not None:
                self.repository.save(audit)

            log_event(
                logger,
                "audit_completed",
                audit_id=audit.audit_id,
                url=stats.seed_url,
                score=score,
                pages=len(pages),
                issues=len(issues),
            )
            return audit
        except Exception as exc:
            log_event(logger, "audit_failed", level=logging.ERROR, url=url, error=str(exc))
            logger.exception("audit_failed")
            raise

    def _apply_options(self, options: AuditOptions) -> Settings:
        settings = deepcopy(self.settings)
        if options.max_pages is not None:
            settings.crawl.max_pages = options.max_pages
        if options.max_depth is not None:
            settings.crawl.max_depth = options.max_depth
        self.crawler_service.settings = settings
        return settings
