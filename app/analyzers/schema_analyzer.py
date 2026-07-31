from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class SchemaAnalyzer:
    """Detect JSON-LD structured data and report discovered schema types."""

    name = "schema"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing = 0
        pages_with_schema = 0
        type_counts: dict[str, int] = {}

        for page in context.pages:
            if page.is_broken:
                continue
            if not page.has_json_ld and not page.schema_types:
                missing += 1
                issues.append(
                    Issue(
                        code="missing_schema",
                        severity=Severity.INFO,
                        message="Page has no JSON-LD structured data",
                        url=page.final_url,
                        details={"extraction_warnings": page.extraction_warnings},
                    )
                )
                continue

            pages_with_schema += 1
            if not page.schema_types:
                issues.append(
                    Issue(
                        code="schema_untyped",
                        severity=Severity.INFO,
                        message="JSON-LD found but no @type values were detected",
                        url=page.final_url,
                    )
                )
            for schema_type in page.schema_types:
                type_counts[schema_type] = type_counts.get(schema_type, 0) + 1

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "pages_missing_schema": missing,
                "pages_with_schema": pages_with_schema,
                "schema_types": type_counts,
                "unique_schema_types": len(type_counts),
            },
        )
