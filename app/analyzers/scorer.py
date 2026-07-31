from __future__ import annotations

from app.config.settings import ScoringSettings
from app.models.issues import AnalyzerResult, Issue, Severity


def aggregate_issues(results: list[AnalyzerResult]) -> list[Issue]:
    issues: list[Issue] = []
    for result in results:
        issues.extend(result.issues)
    return issues


def compute_score(issues: list[Issue], scoring: ScoringSettings) -> float:
    score = float(scoring.base_score)
    for issue in issues:
        if issue.severity == Severity.CRITICAL:
            score -= scoring.weights.critical
        elif issue.severity == Severity.WARNING:
            score -= scoring.weights.warning
        else:
            score -= scoring.weights.info
    return max(0.0, min(100.0, score))


def severity_counts(issues: list[Issue]) -> dict[str, int]:
    counts = {"critical": 0, "warning": 0, "info": 0}
    for issue in issues:
        counts[issue.severity.value] += 1
    return counts
