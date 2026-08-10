"""robots.txt (site-level) + per-page robots meta / indexability."""

from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.config.settings import get_settings
from app.crawler.client import HttpClient
from app.crawler.robots_fetch import fetch_robots_snapshot
from app.models.issues import AnalyzerResult, Issue, Severity
from app.utils.url import normalize_url


class RobotsAnalyzer:
    name = "robots"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        settings = get_settings()
        client = HttpClient(
            user_agent=settings.crawl.user_agent,
            timeout=min(settings.crawl.timeout_seconds, 15.0),
            max_redirects=settings.crawl.max_redirects,
        )
        try:
            snap = fetch_robots_snapshot(
                context.seed_url,
                client,
                user_agent=settings.crawl.user_agent,
            )
        finally:
            client.close()

        issues: list[Issue] = []
        status = snap.get("status")

        if status == "missing":
            issues.append(
                Issue(
                    code="robots_missing",
                    severity=Severity.WARNING,
                    message=(
                        "No robots.txt found at the site origin. Search engines "
                        "fall back to defaults — publish robots.txt and reference "
                        "your XML sitemap with a Sitemap: line."
                    ),
                    url=context.seed_url,
                    details={
                        "robots_url": snap.get("robots_url"),
                        "http_status": snap.get("http_status"),
                    },
                )
            )
        elif status == "error":
            issues.append(
                Issue(
                    code="robots_fetch_error",
                    severity=Severity.INFO,
                    message=(
                        "Could not fetch robots.txt: "
                        + str(snap.get("message") or "unknown error")
                    ),
                    url=context.seed_url,
                    details={"robots_url": snap.get("robots_url")},
                )
            )
        elif status == "ok":
            if snap.get("disallow_all"):
                issues.append(
                    Issue(
                        code="robots_disallow_all",
                        severity=Severity.CRITICAL,
                        message=(
                            "robots.txt Disallow: / blocks all crawlers from the "
                            "site root. The site will not be indexed until this "
                            "is relaxed."
                        ),
                        url=snap.get("robots_url") or context.seed_url,
                        details={"robots_url": snap.get("robots_url")},
                    )
                )
            elif snap.get("seed_allowed") is False:
                issues.append(
                    Issue(
                        code="robots_blocks_seed",
                        severity=Severity.WARNING,
                        message=(
                            "robots.txt disallows the audit seed URL for our "
                            "user-agent. Indexing of this entry point may be blocked."
                        ),
                        url=context.seed_url,
                        details={"robots_url": snap.get("robots_url")},
                    )
                )
            if not snap.get("sitemap_refs"):
                issues.append(
                    Issue(
                        code="robots_no_sitemap_ref",
                        severity=Severity.INFO,
                        message=(
                            "robots.txt has no Sitemap: directive. Add one so "
                            "crawlers can discover your XML sitemap quickly."
                        ),
                        url=snap.get("robots_url") or context.seed_url,
                    )
                )

        noindex = 0
        nofollow = 0
        indexable = 0
        seed_norm = normalize_url(context.seed_url)

        for page in context.pages:
            if page.is_broken:
                continue
            tokens = set()
            if page.robots_meta:
                tokens = {t.strip().lower() for t in page.robots_meta.split(",")}
            page_noindex = "noindex" in tokens
            page_nofollow = "nofollow" in tokens
            if page_noindex:
                noindex += 1
                is_seed = normalize_url(page.final_url or page.url) == seed_norm
                issues.append(
                    Issue(
                        code="robots_noindex",
                        severity=Severity.WARNING if is_seed else Severity.INFO,
                        message=(
                            "Seed/home page has robots meta noindex — this URL "
                            "will not appear in search results."
                            if is_seed
                            else "Page has robots meta noindex"
                        ),
                        url=page.final_url,
                        details={"robots_meta": page.robots_meta},
                    )
                )
            else:
                indexable += 1
            if page_nofollow:
                nofollow += 1
                issues.append(
                    Issue(
                        code="robots_nofollow",
                        severity=Severity.INFO,
                        message="Page has robots meta nofollow",
                        url=page.final_url,
                        details={"robots_meta": page.robots_meta},
                    )
                )

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "robots_txt_status": status,
                "robots_url": snap.get("robots_url"),
                "sitemap_refs": snap.get("sitemap_refs") or [],
                "disallow_all": bool(snap.get("disallow_all")),
                "seed_allowed": snap.get("seed_allowed"),
                "noindex": noindex,
                "nofollow": nofollow,
                "indexable_pages": indexable,
            },
        )
