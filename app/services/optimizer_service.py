from __future__ import annotations

from app.config.settings import Settings, get_settings
from app.extractor.html_extractor import HtmlExtractor
from app.logging import get_logger, log_event
from app.models.audit import SiteAudit
from app.models.optimization import (
    FAQSuggestion,
    InternalLinkSuggestion,
    OptimizationResult,
    PageOptimization,
)
from app.models.page import PageExtraction
from app.optimizer.llm_client import LLMClient, LLMError, OpenAICompatibleClient
from app.optimizer.prompts import build_page_optimization_messages, parse_optimization_json
from app.services.crawler_service import CrawlerService

logger = get_logger(__name__)


class OptimizerService:
    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: LLMClient | None = None,
        crawler_service: CrawlerService | None = None,
        extractor: HtmlExtractor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm_client or OpenAICompatibleClient(
            self.settings.llm, api_key=self.settings.openai_api_key
        )
        self.crawler_service = crawler_service or CrawlerService(self.settings)
        self.extractor = extractor or HtmlExtractor()

    def optimize_page(
        self,
        url: str,
        *,
        target_keywords: list[str] | None = None,
        page: PageExtraction | None = None,
        related_internal_urls: list[str] | None = None,
    ) -> OptimizationResult:
        log_event(logger, "optimize_started", url=url)
        try:
            page_data = page or self._fetch_page(url)
            if page_data.is_broken:
                return OptimizationResult(
                    url=url,
                    status="error",
                    message=page_data.error or "Page could not be fetched",
                )

            related = related_internal_urls or page_data.internal_links
            optimized = self._optimize_extraction(
                page_data,
                target_keywords=target_keywords,
                related_internal_urls=related,
            )
            result = OptimizationResult(
                url=page_data.final_url,
                status="ok",
                message="Optimization suggestions generated",
                target_keywords=target_keywords or [],
                page=optimized,
                pages=[optimized],
            )
            log_event(logger, "optimize_completed", url=page_data.final_url)
            return result
        except LLMError as exc:
            log_event(logger, "optimize_failed", url=url, error=str(exc))
            return OptimizationResult(url=url, status="error", message=str(exc))
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "optimize_failed", url=url, error=str(exc))
            logger.exception("optimize_failed")
            return OptimizationResult(url=url, status="error", message=str(exc))

    def optimize_audit(
        self,
        audit: SiteAudit,
        *,
        target_keywords: list[str] | None = None,
        max_pages: int = 5,
    ) -> OptimizationResult:
        """Generate suggestions for the top N non-broken pages in an audit."""
        related = sorted(
            {p.final_url for p in audit.pages if not p.is_broken}
        )
        pages_out: list[PageOptimization] = []
        errors: list[str] = []

        candidates = [p for p in audit.pages if not p.is_broken][:max_pages]
        for page in candidates:
            try:
                pages_out.append(
                    self._optimize_extraction(
                        page,
                        target_keywords=target_keywords,
                        related_internal_urls=related,
                    )
                )
            except LLMError as exc:
                errors.append(f"{page.final_url}: {exc}")

        status = "ok" if pages_out and not errors else ("partial" if pages_out else "error")
        message = "Optimization suggestions generated"
        if errors:
            message = f"{message}; {len(errors)} page(s) failed"

        return OptimizationResult(
            url=audit.seed_url,
            status=status,
            message=message,
            target_keywords=target_keywords or [],
            page=pages_out[0] if pages_out else None,
            pages=pages_out,
        )

    def _fetch_page(self, url: str) -> PageExtraction:
        # Limit crawl to the single page for optimize_page
        crawl = self.settings.crawl
        original = (
            crawl.max_pages,
            crawl.max_depth,
            crawl.check_external_links,
        )
        crawl.max_pages = 1
        crawl.max_depth = 0
        crawl.check_external_links = False
        self.crawler_service.settings = self.settings
        try:
            results, stats = self.crawler_service.crawl(url)
        finally:
            crawl.max_pages, crawl.max_depth, crawl.check_external_links = original

        pages = self.extractor.extract_many(results, stats.seed_url)
        if not pages:
            return PageExtraction(
                url=url,
                final_url=url,
                is_broken=True,
                error="No page content extracted",
            )
        return pages[0]

    def _optimize_extraction(
        self,
        page: PageExtraction,
        *,
        target_keywords: list[str] | None,
        related_internal_urls: list[str] | None,
    ) -> PageOptimization:
        messages = build_page_optimization_messages(
            page,
            target_keywords=target_keywords,
            related_internal_urls=related_internal_urls,
        )
        raw = self.llm.complete(messages)
        data = parse_optimization_json(raw)

        faqs = [
            FAQSuggestion.model_validate(item)
            for item in data.get("faq_suggestions") or []
            if isinstance(item, dict)
        ]
        links = [
            InternalLinkSuggestion.model_validate(item)
            for item in data.get("internal_link_suggestions") or []
            if isinstance(item, dict)
        ]
        schema = data.get("schema_suggestion")
        if schema is not None and not isinstance(schema, dict):
            schema = {"raw": schema}

        return PageOptimization(
            url=page.final_url,
            improved_title=data.get("improved_title"),
            improved_meta_description=data.get("improved_meta_description"),
            improved_h1=data.get("improved_h1"),
            heading_suggestions=list(data.get("heading_suggestions") or []),
            keyword_suggestions=list(data.get("keyword_suggestions") or []),
            faq_suggestions=faqs,
            schema_suggestion=schema,
            internal_link_suggestions=links,
            notes=list(data.get("notes") or []),
        )
