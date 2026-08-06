"""Image alt-text analysis.

Previously any image whose alt did not contain visible text was reported as
"missing an alt attribute", which conflated three different cases and inflated
counts badly on image-heavy sites (324 findings on one openai.com crawl):

* no alt attribute at all      -> a real accessibility/SEO defect
* alt=""                       -> VALID HTML for decorative images, not a defect
* <source> inside <picture>    -> carries no alt by spec; the sibling <img> does

Only the first is an issue now. Whitespace-only alt is reported separately as a
low-severity hint, since it is sloppy but not the same error.
"""

from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity


class ImageAltAnalyzer:
    name = "image_alt"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing_alt = 0
        whitespace_alt = 0
        decorative = 0
        source_elements = 0
        images_total = 0
        images_checked = 0
        pages_with_images = 0
        pages_missing_alt = 0

        for page in context.pages:
            if page.is_broken or not page.images:
                continue
            pages_with_images += 1
            page_missing = 0

            for image in page.images:
                images_total += 1

                # <source> has no alt attribute in the HTML spec.
                if image.is_source:
                    source_elements += 1
                    continue

                # alt="" / role=presentation / aria-hidden / tracking pixel.
                if image.decorative:
                    decorative += 1
                    continue

                images_checked += 1

                if not image.alt_present:
                    missing_alt += 1
                    page_missing += 1
                    issues.append(
                        Issue(
                            code="missing_image_alt",
                            severity=Severity.WARNING,
                            message="Image has no alt attribute",
                            url=page.final_url,
                            details={
                                "src": image.src,
                                "fix": (
                                    'Add alt="describe the image" — or alt="" if it '
                                    "is purely decorative."
                                ),
                            },
                        )
                    )
                elif not str(image.alt).strip():
                    # alt="   " — present but blank, and not an explicit alt="".
                    whitespace_alt += 1
                    issues.append(
                        Issue(
                            code="whitespace_image_alt",
                            severity=Severity.INFO,
                            message="Image alt attribute contains only whitespace",
                            url=page.final_url,
                            details={
                                "src": image.src,
                                "fix": (
                                    'Use alt="" for decorative images, or describe '
                                    "the image."
                                ),
                            },
                        )
                    )

            if page_missing:
                pages_missing_alt += 1

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "missing_alt": missing_alt,
                "whitespace_alt": whitespace_alt,
                "decorative_images": decorative,
                "source_elements_skipped": source_elements,
                "images_total": images_total,
                "images_checked": images_checked,
                "pages_with_images": pages_with_images,
                "pages_missing_alt": pages_missing_alt,
                # Coverage is measured over images that actually require alt text,
                # so decorative images no longer drag the percentage down.
                "alt_coverage_pct": (
                    round(100 * (images_checked - missing_alt) / images_checked, 1)
                    if images_checked
                    else 100.0
                ),
            },
        )
