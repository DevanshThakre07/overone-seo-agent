from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class ImageAltAnalyzer:
    name = "image_alt"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing_alt = 0
        images_total = 0
        pages_with_images = 0
        pages_missing_alt = 0

        for page in context.pages:
            if page.is_broken:
                continue
            if not page.images:
                continue
            pages_with_images += 1
            page_missing = 0
            for image in page.images:
                images_total += 1
                if image.alt is None or not str(image.alt).strip():
                    missing_alt += 1
                    page_missing += 1
                    issues.append(
                        Issue(
                            code="missing_image_alt",
                            severity=Severity.WARNING,
                            message="Image is missing an alt attribute",
                            url=page.final_url,
                            details={"src": image.src},
                        )
                    )
            if page_missing:
                pages_missing_alt += 1

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "missing_alt": missing_alt,
                "images_total": images_total,
                "pages_with_images": pages_with_images,
                "pages_missing_alt": pages_missing_alt,
                "alt_coverage_pct": (
                    round(100 * (images_total - missing_alt) / images_total, 1)
                    if images_total
                    else 100.0
                ),
            },
        )
