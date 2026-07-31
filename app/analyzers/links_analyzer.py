from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class LinksAnalyzer:
    name = "links"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        broken_pages = 0
        broken_external = 0
        redirect_chains = 0
        internal_unique = 0
        external_unique = 0
        internal_occurrences = 0
        external_occurrences = 0
        pages_without_internal_links = 0

        for page in context.pages:
            internal_unique += len(page.internal_links)
            external_unique += len(page.external_links)
            internal_occurrences += page.internal_link_occurrences or len(page.internal_links)
            external_occurrences += page.external_link_occurrences or len(page.external_links)

            if page.is_broken:
                broken_pages += 1
                issues.append(
                    Issue(
                        code="broken_page",
                        severity=Severity.CRITICAL,
                        message=page.error or "Broken page (HTTP error during crawl)",
                        url=page.final_url,
                        details={
                            "status_code": page.status_code,
                            "requested_url": page.url,
                        },
                    )
                )
            elif not page.internal_links and not page.is_broken:
                pages_without_internal_links += 1
                likely_shell = bool((page.seo_signals or {}).get("likely_js_shell"))
                if likely_shell or page.word_count > 0:
                    issues.append(
                        Issue(
                            code="no_internal_links",
                            severity=Severity.INFO,
                            message="Page has no crawlable internal links",
                            url=page.final_url,
                            details={
                                "word_count": page.word_count,
                                "likely_js_shell": likely_shell,
                                "js_rendered": page.js_rendered,
                            },
                        )
                    )

            if len(page.redirect_chain) > 1:
                redirect_chains += 1
                issues.append(
                    Issue(
                        code="redirect_chain",
                        severity=Severity.WARNING,
                        message=f"Redirect chain with {len(page.redirect_chain)} hops",
                        url=page.url,
                        details={"chain": page.redirect_chain},
                    )
                )

        # External probes stored as crawl_results with depth == -1
        for result in context.crawl_results:
            if result.depth == -1 and result.is_broken:
                broken_external += 1
                issues.append(
                    Issue(
                        code="broken_external_link",
                        severity=Severity.WARNING,
                        message=result.error or "Broken external link",
                        url=result.url,
                        details={"status_code": result.status_code},
                    )
                )

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "broken": broken_pages + broken_external,
                "broken_pages": broken_pages,
                "broken_external_links": broken_external,
                "redirect_chains": redirect_chains,
                "internal_links_unique": internal_unique,
                "external_links_unique": external_unique,
                "internal_link_occurrences": internal_occurrences,
                "external_link_occurrences": external_occurrences,
                "pages_without_internal_links": pages_without_internal_links,
            },
        )
