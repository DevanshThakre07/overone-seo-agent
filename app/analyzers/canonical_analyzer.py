"""Canonical URL presence and indexability conflicts."""

from __future__ import annotations

from urllib.parse import urlparse

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity
from app.utils.url import get_registrable_host, normalize_url


class CanonicalAnalyzer:
    name = "canonical"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing = 0
        cross_host = 0
        mismatch = 0
        self_ref = 0
        seed_norm = normalize_url(context.seed_url)

        for page in context.pages:
            if page.is_broken:
                continue
            page_url = page.final_url or page.url
            page_norm = normalize_url(page_url)
            is_seed = page_norm == seed_norm

            if not page.canonical:
                missing += 1
                issues.append(
                    Issue(
                        code="missing_canonical",
                        severity=Severity.WARNING if is_seed else Severity.INFO,
                        message=(
                            "Seed/home page is missing a canonical link tag"
                            if is_seed
                            else "Page is missing a canonical link tag"
                        ),
                        url=page.final_url,
                    )
                )
                continue

            canon_norm = normalize_url(page.canonical)
            page_host = get_registrable_host(page_url).removeprefix("www.")
            canon_host = get_registrable_host(page.canonical).removeprefix("www.")

            if canon_host and page_host and canon_host != page_host:
                cross_host += 1
                issues.append(
                    Issue(
                        code="canonical_cross_host",
                        severity=Severity.WARNING,
                        message=(
                            "Canonical points to a different host — confirm this "
                            "is intentional (e.g. preferred domain) or fix a "
                            "misconfigured canonical."
                        ),
                        url=page.final_url,
                        details={
                            "canonical": page.canonical,
                            "page_host": page_host,
                            "canonical_host": canon_host,
                        },
                    )
                )
            elif canon_norm == page_norm:
                self_ref += 1
            else:
                # Same host, different path/query — often intentional, but
                # worth surfacing when the page is also noindex (conflict).
                mismatch += 1
                tokens = set()
                if page.robots_meta:
                    tokens = {t.strip().lower() for t in page.robots_meta.split(",")}
                if "noindex" in tokens:
                    issues.append(
                        Issue(
                            code="canonical_noindex_conflict",
                            severity=Severity.WARNING,
                            message=(
                                "Page is noindex but declares a canonical to a "
                                "different URL — consolidate signals so the "
                                "preferred URL is clear."
                            ),
                            url=page.final_url,
                            details={
                                "canonical": page.canonical,
                                "robots_meta": page.robots_meta,
                            },
                        )
                    )
                else:
                    issues.append(
                        Issue(
                            code="canonical_mismatch",
                            severity=Severity.INFO,
                            message=(
                                "Canonical URL differs from the crawled URL "
                                "(same host). Confirm this is the preferred variant."
                            ),
                            url=page.final_url,
                            details={
                                "canonical": page.canonical,
                                "page_path": urlparse(page_url).path,
                                "canonical_path": urlparse(page.canonical).path,
                            },
                        )
                    )

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "missing": missing,
                "self_referencing": self_ref,
                "cross_host": cross_host,
                "mismatch": mismatch,
            },
        )
