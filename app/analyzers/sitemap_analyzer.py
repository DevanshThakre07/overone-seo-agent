from __future__ import annotations

from urllib.parse import urlparse

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class SitemapAnalyzer:
    """Phase 1 skeleton: flags if sitemap.xml was not observed during crawl."""

    name = "sitemap"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        parsed = urlparse(context.seed_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        crawled_urls = {p.final_url for p in context.pages} | {r.final_url for r in context.crawl_results}
        found = any("sitemap.xml" in u for u in crawled_urls)

        issues: list[Issue] = []
        if not found:
            issues.append(
                Issue(
                    code="sitemap_not_checked",
                    severity=Severity.INFO,
                    message=(
                        "Sitemap was not crawled in Phase 1; "
                        f"verify {sitemap_url} manually or enable dedicated sitemap fetch later"
                    ),
                    url=sitemap_url,
                )
            )
        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={"sitemap_observed": found},
        )
