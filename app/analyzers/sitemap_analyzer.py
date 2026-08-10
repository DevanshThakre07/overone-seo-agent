"""Fetch robots.txt Sitemap: + /sitemap.xml and score real coverage."""

from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.config.settings import get_settings
from app.crawler.client import HttpClient
from app.crawler.sitemap import coverage_vs_crawl, fetch_sitemap_snapshot
from app.models.issues import AnalyzerResult, Issue, Severity


class SitemapAnalyzer:
    name = "sitemap"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        settings = get_settings()
        client = HttpClient(
            user_agent=settings.crawl.user_agent,
            timeout=min(settings.crawl.timeout_seconds, 15.0),
            max_redirects=settings.crawl.max_redirects,
        )
        try:
            snap = fetch_sitemap_snapshot(context.seed_url, client)
        finally:
            client.close()

        issues: list[Issue] = []
        crawled = [p.final_url for p in context.pages if not p.is_broken and p.final_url]
        coverage = coverage_vs_crawl(
            snap.get("urls") or [],
            crawled,
            seed_url=context.seed_url,
        )

        status = snap.get("status")
        if status == "missing":
            issues.append(
                Issue(
                    code="sitemap_missing",
                    severity=Severity.WARNING,
                    message=(
                        "No XML sitemap found (robots.txt Sitemap: and /sitemap.xml "
                        "returned 404). Add a sitemap and reference it in robots.txt."
                    ),
                    url=context.seed_url,
                    details={"tried": snap.get("tried") or []},
                )
            )
        elif status == "error":
            issues.append(
                Issue(
                    code="sitemap_fetch_error",
                    severity=Severity.INFO,
                    message=(
                        "Could not fetch or parse a sitemap. "
                        + "; ".join((snap.get("errors") or [])[:3])
                    ),
                    url=context.seed_url,
                    details={"tried": snap.get("tried") or [], "errors": snap.get("errors")},
                )
            )
        elif status == "ok" and int(snap.get("url_count") or 0) == 0:
            issues.append(
                Issue(
                    code="sitemap_empty",
                    severity=Severity.WARNING,
                    message="Sitemap was found but contains no <loc> URLs.",
                    url=(snap.get("source_sitemaps") or [context.seed_url])[0],
                    details={"source_sitemaps": snap.get("source_sitemaps")},
                )
            )
        elif (
            status == "ok"
            and coverage.get("crawled_same_host", 0) > 0
            and coverage.get("missing_count", 0) > 0
        ):
            missing = coverage.get("missing_from_sitemap") or []
            issues.append(
                Issue(
                    code="sitemap_coverage_gap",
                    severity=Severity.INFO,
                    message=(
                        f"{coverage['missing_count']} crawled page(s) are missing from the "
                        f"sitemap (sample: {', '.join(missing[:3])})."
                    ),
                    url=context.seed_url,
                    details=coverage,
                )
            )

        metrics = {
            "sitemap_status": status,
            "sitemap_url_count": snap.get("url_count"),
            "sitemap_sources": snap.get("source_sitemaps") or [],
            "sitemap_tried": snap.get("tried") or [],
            "coverage": {
                k: coverage[k]
                for k in (
                    "crawled_same_host",
                    "in_sitemap",
                    "missing_count",
                    "sitemap_url_count",
                )
                if k in coverage
            },
            # Do not dump full URL list into metrics (can be large).
            "urls_sample": snap.get("urls_sample") or [],
        }
        return AnalyzerResult(analyzer=self.name, issues=issues, metrics=metrics)
