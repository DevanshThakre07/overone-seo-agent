from __future__ import annotations

from collections import defaultdict

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity

TITLE_MIN_LEN = 30
TITLE_MAX_LEN = 60


class TitleAnalyzer:
    name = "title"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        titles: dict[str, list[str]] = defaultdict(list)
        missing = 0
        too_short = 0
        too_long = 0
        fallback_titles = 0
        title_lengths: list[int] = []

        for page in context.pages:
            if page.is_broken:
                continue
            title = (page.title or "").strip()
            if not title:
                missing += 1
                issues.append(
                    Issue(
                        code="missing_title",
                        severity=Severity.CRITICAL,
                        message="Page is missing a title tag (no <title>, og:title, or twitter:title)",
                        url=page.final_url,
                        details={
                            "og_title": page.og_title,
                            "twitter_title": page.twitter_title,
                            "title_source": page.title_source,
                        },
                    )
                )
                continue

            title_lengths.append(len(title))
            titles[title.lower()].append(page.final_url)
            if page.title_source and page.title_source != "title":
                fallback_titles += 1
                issues.append(
                    Issue(
                        code="title_from_fallback",
                        severity=Severity.INFO,
                        message=f"Title taken from {page.title_source} because <title> was empty",
                        url=page.final_url,
                        details={"title": title, "title_source": page.title_source},
                    )
                )

            if len(title) < TITLE_MIN_LEN:
                too_short += 1
                issues.append(
                    Issue(
                        code="title_too_short",
                        severity=Severity.WARNING,
                        message=f"Title is short ({len(title)} chars; aim for {TITLE_MIN_LEN}-{TITLE_MAX_LEN})",
                        url=page.final_url,
                        details={"title": title, "length": len(title)},
                    )
                )
            elif len(title) > TITLE_MAX_LEN:
                too_long += 1
                issues.append(
                    Issue(
                        code="title_too_long",
                        severity=Severity.WARNING,
                        message=f"Title is long ({len(title)} chars; aim for {TITLE_MIN_LEN}-{TITLE_MAX_LEN})",
                        url=page.final_url,
                        details={"title": title, "length": len(title)},
                    )
                )

        duplicates = 0
        for title, urls in titles.items():
            if len(urls) > 1:
                duplicates += 1
                issues.append(
                    Issue(
                        code="duplicate_title",
                        severity=Severity.WARNING,
                        message=f"Duplicate title found on {len(urls)} pages",
                        url=urls[0],
                        details={"title": title, "urls": urls},
                    )
                )

        avg_len = round(sum(title_lengths) / len(title_lengths), 1) if title_lengths else 0.0
        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "missing": missing,
                "duplicates": duplicates,
                "too_short": too_short,
                "too_long": too_long,
                "fallback_titles": fallback_titles,
                "pages_with_title": len(title_lengths),
                "avg_title_length": avg_len,
            },
        )
