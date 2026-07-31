from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class RobotsAnalyzer:
    name = "robots"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        noindex = 0
        for page in context.pages:
            if page.is_broken or not page.robots_meta:
                continue
            tokens = {t.strip().lower() for t in page.robots_meta.split(",")}
            if "noindex" in tokens:
                noindex += 1
                issues.append(
                    Issue(
                        code="robots_noindex",
                        severity=Severity.WARNING,
                        message="Page has robots meta noindex",
                        url=page.final_url,
                        details={"robots_meta": page.robots_meta},
                    )
                )
            if "nofollow" in tokens:
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
            metrics={"noindex": noindex},
        )
