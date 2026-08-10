"""Detect JSON-LD structured data — site-level coverage, not per-page spam."""

from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity
from app.utils.url import normalize_url

# Cap untyped/detail issues so chat/reports stay readable.
_MAX_DETAIL_ISSUES = 5


class SchemaAnalyzer:
    """Detect JSON-LD structured data and report discovered schema types."""

    name = "schema"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing = 0
        pages_with_schema = 0
        type_counts: dict[str, int] = {}
        untyped_urls: list[str] = []
        analyzed = 0
        seed_norm = normalize_url(context.seed_url)
        seed_missing = False

        for page in context.pages:
            if page.is_broken:
                continue
            analyzed += 1
            page_norm = normalize_url(page.final_url or page.url)

            if not page.has_json_ld and not page.schema_types:
                missing += 1
                if page_norm == seed_norm:
                    seed_missing = True
                continue

            pages_with_schema += 1
            if not page.schema_types:
                untyped_urls.append(page.final_url)
            for schema_type in page.schema_types:
                type_counts[schema_type] = type_counts.get(schema_type, 0) + 1

        if analyzed > 0 and missing > 0:
            coverage = pages_with_schema / analyzed
            if seed_missing:
                issues.append(
                    Issue(
                        code="missing_schema",
                        severity=Severity.INFO,
                        message=(
                            "Seed/home page has no JSON-LD structured data. "
                            "Consider Organization/WebSite schema at minimum."
                        ),
                        url=context.seed_url,
                    )
                )
            if missing > 1 or (missing == 1 and not seed_missing):
                issues.append(
                    Issue(
                        code="schema_coverage_low" if coverage < 0.5 else "schema_partial",
                        severity=Severity.INFO,
                        message=(
                            f"{missing}/{analyzed} crawled pages lack JSON-LD "
                            f"({coverage:.0%} coverage). Prefer meaningful types "
                            "(Organization, WebSite, Article, Product, FAQ) on "
                            "key templates — not every URL needs schema."
                        ),
                        url=context.seed_url,
                        details={
                            "pages_missing_schema": missing,
                            "pages_analyzed": analyzed,
                            "coverage": round(coverage, 3),
                        },
                    )
                )

        for url in untyped_urls[:_MAX_DETAIL_ISSUES]:
            issues.append(
                Issue(
                    code="schema_untyped",
                    severity=Severity.INFO,
                    message="JSON-LD found but no @type values were detected",
                    url=url,
                )
            )

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "pages_missing_schema": missing,
                "pages_with_schema": pages_with_schema,
                "pages_analyzed": analyzed,
                "schema_types": type_counts,
                "unique_schema_types": len(type_counts),
                "untyped_count": len(untyped_urls),
            },
        )
