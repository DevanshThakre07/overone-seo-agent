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
from app.optimizer.keyword_research import normalize_caller_keywords
from app.optimizer.llm_client import LLMClient, LLMError, OpenAICompatibleClient
from app.optimizer.prompts import build_page_optimization_messages, parse_optimization_json
from app.services.crawler_service import CrawlerService
from app.services.keyword_planner import analyze_keyword_placement, humanize_fetch_error
from app.utils.integrity import check_url_integrity
from app.utils.scope_guard import build_write_policy

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
                reason = humanize_fetch_error(page_data.error)
                disclaimer = (
                    f"Could not fetch {url} ({reason}) — no analysis was performed. "
                    "Any advice given without this fetch would be generic, NOT "
                    "site-specific. Do not substitute local files or prior knowledge "
                    "for the live page."
                )
                log_event(logger, "optimize_fetch_failed", url=url, error=reason)
                return OptimizationResult(
                    url=url,
                    status="error",
                    message=disclaimer,
                    live_fetch={"ok": False, "url": url, "error": reason},
                    analysis_is_site_specific=False,
                    disclaimer=disclaimer,
                    write_policy=build_write_policy(url),
                )

            related = related_internal_urls or page_data.internal_links
            keyword_meta = normalize_caller_keywords(target_keywords)
            optimized = self._optimize_extraction(
                page_data,
                target_keywords=keyword_meta["keywords"] or None,
                related_internal_urls=related,
                keyword_research_status=keyword_meta,
            )
            # Never present invented / scraped words as researched keywords.
            if not keyword_meta.get("is_real_research"):
                if keyword_meta["status"] != "caller_provided_not_researched":
                    optimized.keyword_suggestions = []
                optimized.notes = list(optimized.notes) + [
                    keyword_meta.get("message")
                    or keyword_meta.get("research", {}).get("message")
                    or "Keyword research API is not configured."
                ]
            placement = analyze_keyword_placement(page_data, keyword_meta["keywords"])
            result = OptimizationResult(
                url=page_data.final_url,
                status="ok",
                message="Optimization suggestions generated from a live fetch of the page",
                target_keywords=keyword_meta["keywords"],
                keyword_research=keyword_meta,
                page=optimized,
                pages=[optimized],
                live_fetch={
                    "ok": True,
                    "url": url,
                    "final_url": page_data.final_url,
                    "status_code": page_data.status_code,
                    "js_rendered": page_data.js_rendered,
                    "method": "playwright" if page_data.js_rendered else "http",
                    "word_count": page_data.word_count,
                },
                page_evidence={
                    "title": page_data.title,
                    "meta_description": page_data.meta_description,
                    "h1": page_data.h1,
                    "h2": page_data.h2[:10],
                    "word_count": page_data.word_count,
                    "text_excerpt": (page_data.text_sample or "")[:400],
                },
                url_integrity=check_url_integrity(
                    url, [page_data.final_url], redirect_chains=[page_data.redirect_chain]
                ),
                keyword_placement={
                    "findings": placement[0],
                    "placements": placement[1],
                },
                analysis_is_site_specific=True,
                write_policy=build_write_policy(url),
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
        keyword_meta = normalize_caller_keywords(target_keywords)

        candidates = [p for p in audit.pages if not p.is_broken][:max_pages]
        for page in candidates:
            try:
                optimized = self._optimize_extraction(
                    page,
                    target_keywords=keyword_meta["keywords"] or None,
                    related_internal_urls=related,
                    keyword_research_status=keyword_meta,
                )
                if not keyword_meta.get("is_real_research"):
                    if keyword_meta["status"] != "caller_provided_not_researched":
                        optimized.keyword_suggestions = []
                    optimized.notes = list(optimized.notes) + [
                        keyword_meta.get("message")
                        or keyword_meta.get("research", {}).get("message")
                        or "Keyword research API is not configured."
                    ]
                pages_out.append(optimized)
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
            target_keywords=keyword_meta["keywords"],
            keyword_research=keyword_meta,
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
        keyword_research_status: dict | None = None,
    ) -> PageOptimization:
        messages = build_page_optimization_messages(
            page,
            target_keywords=target_keywords,
            related_internal_urls=related_internal_urls,
            keyword_research_status=keyword_research_status,
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
