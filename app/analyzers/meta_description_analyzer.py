from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity

META_MIN_LEN = 70
META_MAX_LEN = 160


class MetaDescriptionAnalyzer:
    name = "meta_description"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing = 0
        too_short = 0
        too_long = 0
        fallback = 0
        lengths: list[int] = []

        for page in context.pages:
            if page.is_broken:
                continue
            desc = (page.meta_description or "").strip()
            if not desc:
                missing += 1
                issues.append(
                    Issue(
                        code="missing_meta_description",
                        severity=Severity.WARNING,
                        message="Page is missing a meta description (no name=description, og:description, or twitter:description)",
                        url=page.final_url,
                        details={
                            "og_description": page.og_description,
                            "twitter_description": page.twitter_description,
                        },
                    )
                )
                continue

            lengths.append(len(desc))
            if page.meta_description_source and page.meta_description_source != "description":
                fallback += 1
                issues.append(
                    Issue(
                        code="meta_description_from_fallback",
                        severity=Severity.INFO,
                        message=(
                            f"Meta description taken from {page.meta_description_source} "
                            "because name=description was empty"
                        ),
                        url=page.final_url,
                        details={
                            "meta_description": desc,
                            "source": page.meta_description_source,
                        },
                    )
                )

            if len(desc) < META_MIN_LEN:
                too_short += 1
                issues.append(
                    Issue(
                        code="meta_description_too_short",
                        severity=Severity.INFO,
                        message=f"Meta description is short ({len(desc)} chars; aim for {META_MIN_LEN}-{META_MAX_LEN})",
                        url=page.final_url,
                        details={"meta_description": desc, "length": len(desc)},
                    )
                )
            elif len(desc) > META_MAX_LEN:
                too_long += 1
                issues.append(
                    Issue(
                        code="meta_description_too_long",
                        severity=Severity.INFO,
                        message=f"Meta description is long ({len(desc)} chars; aim for {META_MIN_LEN}-{META_MAX_LEN})",
                        url=page.final_url,
                        details={"meta_description": desc, "length": len(desc)},
                    )
                )

        avg_len = round(sum(lengths) / len(lengths), 1) if lengths else 0.0
        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "missing": missing,
                "too_short": too_short,
                "too_long": too_long,
                "fallback_descriptions": fallback,
                "pages_with_meta_description": len(lengths),
                "avg_meta_description_length": avg_len,
            },
        )
