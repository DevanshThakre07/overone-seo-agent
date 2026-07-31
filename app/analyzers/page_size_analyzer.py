from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class PageSizeAnalyzer:
    name = "page_size"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        threshold = context.config.page_size_threshold_bytes
        issues: list[Issue] = []
        large = 0
        for page in context.pages:
            if page.is_broken:
                continue
            if page.content_length >= threshold:
                large += 1
                issues.append(
                    Issue(
                        code="large_page",
                        severity=Severity.WARNING,
                        message=f"Page is large ({page.content_length} bytes)",
                        url=page.final_url,
                        details={
                            "content_length": page.content_length,
                            "threshold": threshold,
                        },
                    )
                )
        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={"large_pages": large, "threshold": threshold},
        )
