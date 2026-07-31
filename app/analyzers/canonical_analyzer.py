from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class CanonicalAnalyzer:
    name = "canonical"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing = 0
        for page in context.pages:
            if page.is_broken:
                continue
            if not page.canonical:
                missing += 1
                issues.append(
                    Issue(
                        code="missing_canonical",
                        severity=Severity.INFO,
                        message="Page is missing a canonical link tag",
                        url=page.final_url,
                    )
                )
        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={"missing": missing},
        )
