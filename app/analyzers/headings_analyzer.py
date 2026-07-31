from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class HeadingsAnalyzer:
    name = "headings"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing_h1 = 0
        multiple_h1 = 0
        empty_h1_filtered = 0
        pages_with_h2 = 0
        total_h1 = 0
        total_h2 = 0
        total_h3 = 0

        for page in context.pages:
            if page.is_broken:
                continue

            h1 = [h.strip() for h in page.h1 if h and str(h).strip()]
            h2 = [h.strip() for h in page.h2 if h and str(h).strip()]
            h3 = [h.strip() for h in page.h3 if h and str(h).strip()]
            total_h1 += len(h1)
            total_h2 += len(h2)
            total_h3 += len(h3)
            if h2:
                pages_with_h2 += 1
            if len(page.h1) != len(h1):
                empty_h1_filtered += len(page.h1) - len(h1)

            if not h1:
                missing_h1 += 1
                likely_shell = bool((page.seo_signals or {}).get("likely_js_shell"))
                message = "Page is missing an H1 heading"
                if likely_shell and not page.js_rendered:
                    message += " (page looks like a JS shell; enable Playwright for client-rendered content)"
                issues.append(
                    Issue(
                        code="missing_h1",
                        severity=Severity.CRITICAL,
                        message=message,
                        url=page.final_url,
                        details={
                            "h2_count": len(h2),
                            "h3_count": len(h3),
                            "word_count": page.word_count,
                            "js_rendered": page.js_rendered,
                            "likely_js_shell": likely_shell,
                        },
                    )
                )
            elif len(h1) > 1:
                multiple_h1 += 1
                issues.append(
                    Issue(
                        code="multiple_h1",
                        severity=Severity.INFO,
                        message=f"Page has {len(h1)} H1 headings",
                        url=page.final_url,
                        details={"h1": h1},
                    )
                )

            # Flag skipped heading levels only when deeper headings exist without H2.
            if h1 and not h2 and h3:
                issues.append(
                    Issue(
                        code="skipped_heading_level",
                        severity=Severity.INFO,
                        message="Page has H3 headings without any H2 (possible heading hierarchy skip)",
                        url=page.final_url,
                        details={"h1": h1, "h3": h3[:10]},
                    )
                )

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "missing_h1": missing_h1,
                "multiple_h1": multiple_h1,
                "empty_h1_filtered": empty_h1_filtered,
                "pages_with_h2": pages_with_h2,
                "total_h1": total_h1,
                "total_h2": total_h2,
                "total_h3": total_h3,
            },
        )
