from __future__ import annotations

import logging
from copy import deepcopy

from app.analyzers.base import AnalysisContext
from app.analyzers.metrics import build_structured_seo_metrics
from app.analyzers.recommendations import (
    build_prescriptive_recommendations,
    merge_gsc_into_recommendations,
)
from app.analyzers.registry import AnalyzerRegistry, build_default_registry
from app.analyzers.rendering_guardrails import apply_rendering_guardrails
from app.analyzers.scorer import (
    aggregate_issues,
    compute_score_breakdown,
    severity_counts,
)
from app.config.settings import Settings, get_settings
from app.crawler.auth import auth_policy_block, build_crawl_auth
from app.extractor.html_extractor import HtmlExtractor
from app.logging import get_logger, log_event
from app.models.audit import AuditOptions, SiteAudit
from app.models.issues import Issue, Severity
from app.optimizer.keyword_research import normalize_caller_keywords
from app.repositories.base import AuditRepository
from app.services.crawler_service import CrawlerService
from app.services.memory_service import MemoryService
from app.services.optimizer_service import OptimizerService
from app.utils.integrity import check_url_integrity
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

        # Auth: in-memory only. Probe login wall WITHOUT credentials first.
        crawl_auth = build_crawl_auth(
            auth_cookie=options.auth_cookie,
            auth_headers=options.auth_headers or None,
        )
        use_auth = bool(options.use_authenticated_crawl) and bool(crawl_auth)
        login_wall = self.crawler_service.probe_login_wall(url)
        auth_meta = auth_policy_block(
            auth=crawl_auth,
            use_authenticated_crawl=bool(options.use_authenticated_crawl),
            login_wall=login_wall,
            credentials_used=use_auth,
        )
        if options.use_authenticated_crawl and not crawl_auth:
            log_event(logger, "auth_opt_in_without_credentials", url=url)
        if crawl_auth and not options.use_authenticated_crawl:
            log_event(
                logger,
                "auth_credentials_ignored_until_opt_in",
                url=url,
                credentials_supplied=True,
            )

        try:
            crawl_results, stats = self.crawler_service.crawl(
                url,
                auth=crawl_auth if use_auth else None,
            )
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

            # Suppress false content findings on unrendered JS shells and surface
            # a top-level rendering warning instead of burying it.
            issues, analyzer_results, rendering_meta = apply_rendering_guardrails(
                pages, issues, analyzer_results
            )

            if login_wall.get("requires_login") and not use_auth:
                issues.insert(
                    0,
                    Issue(
                        code="login_wall_detected",
                        severity=Severity.INFO,
                        message=(
                            "Login wall detected on a public fetch. Authenticated pages "
                            "were not crawled. Opt in with use_authenticated_crawl=true "
                            "and auth_cookie/auth_headers (GET-only, in-memory credentials)."
                        ),
                        url=normalize_url(url),
                        details={
                            "signals": login_wall.get("signals"),
                            "credentials_supplied": bool(crawl_auth),
                            "use_authenticated_crawl": bool(
                                options.use_authenticated_crawl
                            ),
                        },
                    ),
                )

            # Defense-in-depth: never return data for a page other than the one
            # that was asked for (guards against cross-run/cached mixups).
            url_integrity = check_url_integrity(
                url,
                [p.final_url for p in pages],
                redirect_chains=[p.redirect_chain for p in pages],
            )
            if not url_integrity["ok"]:
                log_event(
                    logger,
                    "url_integrity_failed",
                    requested=url,
                    observed=url_integrity["observed_urls"],
                )
                issues.insert(
                    0,
                    Issue(
                        code="url_integrity_mismatch",
                        severity=Severity.CRITICAL,
                        message=url_integrity["warning"],
                        url=url,
                        details={"observed_urls": url_integrity["observed_urls"]},
                    ),
                )

            # PageSpeed Insights on the seed URL (optional, never fails the audit).
            pagespeed_block: dict = {
                "status": "skipped",
                "message": "PageSpeed not requested for this audit.",
            }
            run_pagespeed = options.pagespeed
            if run_pagespeed is None:
                run_pagespeed = bool(
                    settings.pagespeed.enabled and settings.pagespeed.api_key
                )
            if run_pagespeed:
                try:
                    from app.integrations.google.pagespeed_service import PageSpeedService

                    pagespeed_block, psi_issues = PageSpeedService(settings).audit_enrichment(
                        stats.seed_url,
                        run=True,
                    )
                    issues.extend(psi_issues)
                except Exception as exc:  # noqa: BLE001
                    log_event(
                        logger,
                        "pagespeed_enrichment_exception",
                        url=stats.seed_url,
                        error=str(exc),
                    )
                    pagespeed_block = {
                        "status": "error",
                        "url": stats.seed_url,
                        "message": str(exc),
                    }
            elif not settings.pagespeed.api_key:
                pagespeed_block = {
                    "status": "skipped",
                    "message": (
                        "GOOGLE_PAGESPEED_API_KEY is not set. "
                        "Enable PageSpeed Insights API and add the key to get Core Web Vitals."
                    ),
                }

            score_breakdown = compute_score_breakdown(
                issues,
                settings.analyzer.scoring,
                pages_analyzed=len(pages),
            )
            raw_score = score_breakdown["score"]
            rendering_incomplete = bool(rendering_meta.get("rendering_incomplete"))
            # Do not present a confident score when the DOM was not rendered.
            if rendering_incomplete:
                score = raw_score  # retained for storage/debug only
                score_status = "provisional"
                score_note = (
                    "PROVISIONAL — based on incomplete rendering data. "
                    "Do not treat this score as a reliable SEO grade until "
                    "Playwright successfully captures the rendered DOM."
                )
            else:
                score = raw_score
                score_status = "final"
                score_note = None
            counts = severity_counts(issues)
            recommendations = build_prescriptive_recommendations(pages)
            scope = self._build_scope(stats.seed_url, pages, settings, stats)
            render_diagnostics = [
                {
                    "url": p.final_url,
                    "js_rendered": p.js_rendered,
                    "word_count": p.word_count,
                    "diagnostics": (p.seo_signals or {}).get("render_diagnostics") or {},
                }
                for p in pages
            ]

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
            seo_metrics["rendering"] = {
                **(seo_metrics.get("rendering") or {}),
                **rendering_meta,
            }

            gsc_block: dict = {
                "status": "skipped",
                "message": (
                    "No gsc_account_id provided. Technical crawl audit only. "
                    "Customers connect Google via /auth/google/start, then pass "
                    "their account_id to enrich with Search Console data."
                ),
            }
            if options.gsc_account_id:
                try:
                    from app.integrations.google.service import GoogleSearchConsoleService

                    gsc_block = GoogleSearchConsoleService(settings).audit_enrichment(
                        options.gsc_account_id,
                        stats.seed_url,
                    )
                except Exception as exc:  # noqa: BLE001 — never fail the audit on GSC
                    log_event(
                        logger,
                        "gsc_enrichment_exception",
                        account_id=options.gsc_account_id,
                        error=str(exc),
                    )
                    gsc_block = {
                        "status": "error",
                        "account_id": options.gsc_account_id,
                        "message": str(exc),
                    }

            recommendations = merge_gsc_into_recommendations(recommendations, gsc_block)

            ga4_block: dict = {
                "status": "skipped",
                "message": (
                    "GA4 not requested. Pass include_ga4=true with "
                    "gsc_account_id + ga4_property_id (from /ga4/properties)."
                ),
            }
            if options.include_ga4:
                try:
                    from app.integrations.google.ga4_service import Ga4Service

                    ga4_block = Ga4Service(settings).audit_enrichment(
                        options.gsc_account_id,
                        options.ga4_property_id,
                    )
                except Exception as exc:  # noqa: BLE001 — never fail the audit on GA4
                    log_event(
                        logger,
                        "ga4_enrichment_exception",
                        account_id=options.gsc_account_id,
                        property_id=options.ga4_property_id,
                        error=str(exc),
                    )
                    ga4_block = {
                        "status": "error",
                        "account_id": options.gsc_account_id,
                        "property_id": options.ga4_property_id,
                        "message": str(exc),
                    }

            # Phase 2 competitive — opt-in only (paid). Never auto.
            serp_block: dict = {
                "status": "skipped",
                "message": (
                    "Competitive SERP/rank not requested. Pass include_serp=true "
                    "with target_keywords, or call /serp and /rank directly."
                ),
            }
            backlinks_block: dict = {
                "status": "skipped",
                "message": (
                    "Backlinks not requested. Pass include_backlinks=true, "
                    "or call /backlinks directly."
                ),
            }
            if options.include_serp or options.include_backlinks:
                from app.integrations.dataforseo.competitive import CompetitiveSeoService

                competitive = CompetitiveSeoService(settings)
                if options.include_serp:
                    try:
                        serp_block = competitive.audit_serp_enrichment(
                            stats.seed_url,
                            options.target_keywords or [],
                        )
                    except Exception as exc:  # noqa: BLE001
                        log_event(
                            logger,
                            "serp_enrichment_exception",
                            error=str(exc),
                        )
                        serp_block = {
                            "status": "error",
                            "message": str(exc),
                        }
                if options.include_backlinks:
                    try:
                        backlinks_block = competitive.audit_backlinks_enrichment(
                            stats.seed_url
                        )
                    except Exception as exc:  # noqa: BLE001
                        log_event(
                            logger,
                            "backlinks_enrichment_exception",
                            error=str(exc),
                        )
                        backlinks_block = {
                            "status": "error",
                            "message": str(exc),
                        }

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
                    "seo_metrics": seo_metrics,
                    "scope": scope,
                    "rendering": {
                        **rendering_meta,
                        "page_diagnostics": render_diagnostics,
                    },
                    "recommendations": recommendations,
                    "score_status": score_status,
                    "score_note": score_note,
                    "raw_score": raw_score,
                    "score_breakdown": score_breakdown,
                    "url_integrity": url_integrity,
                    # Always present so reports can never imply keywords were researched.
                    "keyword_research": normalize_caller_keywords(options.target_keywords),
                    "google_search_console": gsc_block,
                    "google_analytics": ga4_block,
                    "pagespeed": pagespeed_block,
                    "serp": serp_block,
                    "backlinks": backlinks_block,
                    # Never includes cookie/header values — redacted policy only.
                    "crawl_auth": auth_meta,
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
                audit.summary["keyword_research"] = audit.optimization.keyword_research

            if options.compare and self.memory_service is not None:
                audit.diff = self.memory_service.compare(audit, previous=previous)
                audit.summary["compare"] = {
                    "has_baseline": audit.diff.has_baseline,
                    "score_delta": audit.diff.score_delta,
                    "new_issues": len(audit.diff.new_issues),
                    "resolved_issues": len(audit.diff.resolved_issues),
                }

            # Rank history — independent of full-audit save; only when SERP ran ok.
            if serp_block.get("status") == "ok":
                try:
                    from app.repositories.factory import get_rank_history_repository
                    from app.services.rank_history_service import RankHistoryService

                    RankHistoryService(get_rank_history_repository(settings)).record_serp_block(
                        serp_block,
                        seed_url=audit.seed_url,
                        audit_id=audit.audit_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    log_event(
                        logger,
                        "rank_history_record_failed",
                        error=str(exc),
                        audit_id=audit.audit_id,
                    )

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

    def _build_scope(self, seed_url: str, pages, settings: Settings, stats) -> dict:
        live = [p for p in pages if not p.is_broken]
        n = len(pages)
        max_pages = settings.crawl.max_pages
        max_depth = settings.crawl.max_depth
        if n <= 1:
            note = (
                f"SCOPE LIMITATION: This audit analyzed only the given URL "
                f"({seed_url}) — not a full-site crawl. "
                f"Crawl limits were max_pages={max_pages}, max_depth={max_depth}."
            )
        else:
            note = (
                f"This audit analyzed {n} page(s) starting from {seed_url} "
                f"(crawl limits: max_pages={max_pages}, max_depth={max_depth}; "
                f"discovered≈{getattr(stats, 'pages_discovered', n)}). "
                "This is not necessarily a complete site inventory."
            )
        return {
            "seed_url": seed_url,
            "pages_analyzed": n,
            "pages_live": len(live),
            "max_pages_limit": max_pages,
            "max_depth_limit": max_depth,
            "pages_discovered": getattr(stats, "pages_discovered", n),
            "note": note,
        }
