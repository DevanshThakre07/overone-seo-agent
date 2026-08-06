"""Issue aggregation and scoring.

The original formula subtracted a flat weight per issue from a fixed base of
100. Issue counts scale with pages crawled but the budget did not, so a 50-page
audit of openai.com produced a raw score of -1247 (clamped to 0.0) — 324
`missing_image_alt` warnings alone cost 972 points. The score measured crawl
size, not site quality.

Three corrections:

1. Page-level penalties scale with *prevalence* (how many of the crawled pages
   are affected), not with raw occurrence count. Site-level findings (sitemap,
   robots, rendering, integrity) are charged once, undivided.
2. Repeated occurrences on the same page do not stack, so one systemic problem
   costs a firm, bounded amount instead of n independent failures.
3. Every component is reported in a breakdown, including the pre-clamp raw
   score, so a score can always be explained.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.config.settings import ScoringSettings
from app.models.issues import AnalyzerResult, Issue, Severity

# Findings about the site as a whole. Charged once regardless of page count,
# because they do not repeat per page in a meaningful way.
SITE_LEVEL_CODES = frozenset(
    {
        "sitemap_not_checked",
        "sitemap_missing",
        "robots_missing",
        "robots_disallow_all",
        "rendering_incomplete",
        "url_integrity_mismatch",
    }
)

# Reported for visibility but never scored. Redirect chains are frequently
# legitimate (locale, trailing slash, http->https) and 48 of them on a large
# site is not a quality defect worth 144 points.
INFORMATIONAL_ONLY_CODES = frozenset(
    {
        "redirect_chain",
    }
)

# Defaults, overridable via ScoringSettings (config/default.yaml).
# Ceiling for the page-level component so no volume of issues can consume the
# whole scale. Site-level issues are charged on top of this.
MAX_PAGE_LEVEL_PENALTY = 60.0

# Cost of a page-level issue present on EVERY crawled page, per unit of
# severity weight. At 3.0 a fully-prevalent warning (weight 3) costs 9 points
# and a fully-prevalent critical (weight 8) costs 24.
PREVALENCE_SCALE = 3.0

# Prevalence needs a sample to be meaningful. On a 1-page crawl every finding is
# trivially "100% prevalent", which punished small audits for having no larger
# page-set to dilute against — an artifact of sample size, not a real signal.
# Below this threshold, charge the severity weight flat instead.
MIN_PAGES_FOR_PREVALENCE = 5


def aggregate_issues(results: list[AnalyzerResult]) -> list[Issue]:
    issues: list[Issue] = []
    for result in results:
        issues.extend(result.issues)
    return issues


def _weight_for(severity: Severity, scoring: ScoringSettings) -> int:
    if severity == Severity.CRITICAL:
        return scoring.weights.critical
    if severity == Severity.WARNING:
        return scoring.weights.warning
    return scoring.weights.info


def compute_score_breakdown(
    issues: list[Issue],
    scoring: ScoringSettings,
    *,
    pages_analyzed: int = 1,
) -> dict[str, Any]:
    """Score the audit and explain every component of the result."""
    pages = max(1, pages_analyzed)
    scale = getattr(scoring, "prevalence_scale", PREVALENCE_SCALE)
    page_cap = getattr(scoring, "max_page_level_penalty", MAX_PAGE_LEVEL_PENALTY)
    min_pages = getattr(scoring, "min_pages_for_prevalence", MIN_PAGES_FOR_PREVALENCE)
    use_prevalence = pages >= min_pages
    severity_by_code: dict[str, Severity] = {}
    counts: Counter[str] = Counter()
    affected: defaultdict[str, set[str]] = defaultdict(set)
    for issue in issues:
        counts[issue.code] += 1
        # Repeated occurrences on one page must not stack, so track the set of
        # distinct pages a code affects.
        affected[issue.code].add(issue.url or "<site>")
        # Worst severity seen for a code wins.
        current = severity_by_code.get(issue.code)
        if current is None or _severity_rank(issue.severity) > _severity_rank(current):
            severity_by_code[issue.code] = issue.severity

    components: list[dict[str, Any]] = []
    page_penalty = 0.0
    site_penalty = 0.0

    for code, count in counts.most_common():
        severity = severity_by_code[code]
        weight = _weight_for(severity, scoring)
        pages_affected = len(affected[code])

        if code in INFORMATIONAL_ONLY_CODES:
            components.append(
                {
                    "code": code,
                    "count": count,
                    "pages_affected": pages_affected,
                    "severity": severity.value,
                    "scope": "informational",
                    "weight": weight,
                    "penalty": 0.0,
                    "scored": False,
                    "note": (
                        "Reported for visibility only — not scored. "
                        f"{count} occurrence(s) across {pages_affected} page(s); "
                        "review if this number looks suspicious."
                    ),
                }
            )
            continue

        if code in SITE_LEVEL_CODES:
            penalty = float(weight)
            site_penalty += penalty
            components.append(
                {
                    "code": code,
                    "count": count,
                    "pages_affected": pages_affected,
                    "severity": severity.value,
                    "scope": "site",
                    "weight": weight,
                    "penalty": round(penalty, 2),
                    "scored": True,
                }
            )
            continue

        prevalence = min(1.0, pages_affected / pages)
        if use_prevalence:
            penalty = weight * prevalence * scale
        else:
            # Small crawl: charge the weight once per affected page. Repeated
            # occurrences on one page still do not stack.
            penalty = float(weight * pages_affected)
        page_penalty += penalty
        components.append(
            {
                "code": code,
                "count": count,
                "pages_affected": pages_affected,
                "severity": severity.value,
                "scope": "page",
                "weight": weight,
                "prevalence": round(prevalence, 3),
                "mode": "prevalence" if use_prevalence else "flat",
                "old_flat_penalty": round(weight * count, 2),
                "penalty": round(penalty, 2),
                "scored": True,
            }
        )

    capped_page_penalty = min(page_penalty, page_cap)
    total_penalty = capped_page_penalty + site_penalty
    raw_score = float(scoring.base_score) - total_penalty
    score = max(0.0, min(100.0, raw_score))

    return {
        "score": round(score, 1),
        "raw_score": round(raw_score, 2),
        "base_score": float(scoring.base_score),
        "pages_analyzed": pages,
        "issues_total": len(issues),
        "issues_scored": sum(
            c for code, c in counts.items() if code not in INFORMATIONAL_ONLY_CODES
        ),
        "issues_informational": sum(
            c for code, c in counts.items() if code in INFORMATIONAL_ONLY_CODES
        ),
        "page_level_penalty": round(page_penalty, 2),
        "page_level_penalty_capped": round(capped_page_penalty, 2),
        "page_level_cap": page_cap,
        "page_level_cap_hit": page_penalty > page_cap,
        "prevalence_scale": scale,
        "scoring_mode": "prevalence" if use_prevalence else "flat_small_crawl",
        "min_pages_for_prevalence": min_pages,
        "scoring_mode_note": (
            f"{pages} page(s) analyzed — prevalence weighting applied."
            if use_prevalence
            else (
                f"Only {pages} page(s) analyzed (threshold {min_pages}). Prevalence is "
                "not meaningful on a sample this small, so severity weights are charged "
                "flat per affected page instead of being scaled by prevalence."
            )
        ),
        "site_level_penalty": round(site_penalty, 2),
        "total_penalty": round(total_penalty, 2),
        "clamped": raw_score < 0.0 or raw_score > 100.0,
        "weights": {
            "critical": scoring.weights.critical,
            "warning": scoring.weights.warning,
            "info": scoring.weights.info,
        },
        "components": components,
    }


def compute_score(
    issues: list[Issue],
    scoring: ScoringSettings,
    *,
    pages_analyzed: int = 1,
) -> float:
    return compute_score_breakdown(
        issues, scoring, pages_analyzed=pages_analyzed
    )["score"]


def _severity_rank(severity: Severity) -> int:
    return {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}.get(severity, 0)


def severity_counts(issues: list[Issue]) -> dict[str, int]:
    counts = {"critical": 0, "warning": 0, "info": 0}
    for issue in issues:
        counts[issue.severity.value] += 1
    return counts
