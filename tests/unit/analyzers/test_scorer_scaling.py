"""Scoring regressions for multi-page audits.

The bug: openai.com at 50 pages produced 482 issues, a raw score of -1247, and
a reported score of exactly 0.0. 324 `missing_image_alt` warnings alone cost 972
points against a 100-point budget, so the score measured crawl size rather than
site quality.
"""

from __future__ import annotations

from app.analyzers.scorer import (
    INFORMATIONAL_ONLY_CODES,
    MAX_PAGE_LEVEL_PENALTY,
    compute_score,
    compute_score_breakdown,
)
from app.config.settings import ScoringSettings
from app.models.issues import Issue, Severity

SCORING = ScoringSettings()


def _issues(code: str, severity: Severity, n: int, *, pages: int | None = None):
    """n occurrences spread over `pages` distinct URLs (default: one page each)."""
    spread = pages if pages is not None else n
    return [
        Issue(
            code=code,
            severity=severity,
            message=f"{code} #{i}",
            url=f"https://example.com/p{i % max(1, spread)}",
        )
        for i in range(n)
    ]


class TestRegressionLowSeverityFlood:
    """The case that would have caught the original bug."""

    def test_300_low_severity_issues_do_not_zero_the_score(self):
        issues = _issues("missing_image_alt", Severity.INFO, 324, pages=50)
        score = compute_score(issues, SCORING, pages_analyzed=50)
        assert score > 50.0, f"324 info issues must not tank the score, got {score}"

    def test_the_actual_openai_shape_scores_reasonably(self):
        issues = (
            _issues("missing_image_alt", Severity.WARNING, 324, pages=15)
            + _issues("missing_schema", Severity.INFO, 49, pages=49)
            + _issues("title_too_short", Severity.WARNING, 20, pages=20)
            + _issues("missing_h1", Severity.CRITICAL, 7, pages=7)
        )
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=50)
        assert 60.0 <= b["score"] <= 90.0, b["score"]
        assert b["clamped"] is False
        assert b["raw_score"] > 0

    def test_issue_volume_can_no_longer_drive_the_score_to_zero(self):
        """Strongest guarantee: with the cap, an exact 0.0 from volume is impossible.

        Previously 482 issues produced raw -1247 -> clamped 0.0. Page-level
        penalties are now bounded, so a real site always gets a usable grade.
        """
        issues = _issues("missing_h1", Severity.CRITICAL, 5000, pages=5000)
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=1)
        assert b["score"] > 0.0, "score must never collapse to 0 from volume alone"
        assert b["clamped"] is False

    def test_raw_score_is_always_exposed_and_consistent(self):
        """The old code stored the clamped value, discarding the real figure."""
        issues = _issues("missing_h1", Severity.CRITICAL, 3, pages=3)
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=10)
        assert b["raw_score"] == b["base_score"] - b["total_penalty"]
        assert b["total_penalty"] == (
            b["page_level_penalty_capped"] + b["site_level_penalty"]
        )


class TestPageCountNormalization:
    def test_same_prevalence_scores_the_same_at_any_crawl_size(self):
        """A 5-page and a 100-page crawl of an equally-flawed site must agree."""
        small = compute_score(
            _issues("title_too_short", Severity.WARNING, 5, pages=5),
            SCORING,
            pages_analyzed=5,
        )
        large = compute_score(
            _issues("title_too_short", Severity.WARNING, 100, pages=100),
            SCORING,
            pages_analyzed=100,
        )
        assert abs(small - large) < 0.1, (small, large)

    def test_more_pages_crawled_does_not_lower_the_score_by_itself(self):
        """The original bug: score fell purely because more pages were crawled.

        Compared within prevalence mode; the small-crawl threshold is a
        deliberate mode change covered by TestSmallCrawlThreshold.
        """
        five = compute_score(
            _issues("missing_image_alt", Severity.WARNING, 5, pages=5),
            SCORING,
            pages_analyzed=5,
        )
        fifty = compute_score(
            _issues("missing_image_alt", Severity.WARNING, 50, pages=50),
            SCORING,
            pages_analyzed=50,
        )
        assert fifty >= five - 0.1, (five, fifty)

    def test_repeat_occurrences_on_one_page_do_not_stack(self):
        many_on_one = _issues("missing_image_alt", Severity.WARNING, 60, pages=1)
        one_on_one = _issues("missing_image_alt", Severity.WARNING, 1, pages=1)
        assert compute_score(
            many_on_one, SCORING, pages_analyzed=10
        ) == compute_score(one_on_one, SCORING, pages_analyzed=10)

    def test_prevalence_drives_the_penalty(self):
        """Affecting every page must cost more than affecting a few."""
        widespread = compute_score(
            _issues("title_too_short", Severity.WARNING, 50, pages=50),
            SCORING,
            pages_analyzed=50,
        )
        isolated = compute_score(
            _issues("title_too_short", Severity.WARNING, 2, pages=2),
            SCORING,
            pages_analyzed=50,
        )
        assert isolated > widespread


class TestSmallCrawlThreshold:
    """Prevalence is meaningless below a minimum sample size."""

    def test_single_page_uses_flat_mode(self):
        b = compute_score_breakdown(
            _issues("missing_h1", Severity.CRITICAL, 1, pages=1),
            SCORING,
            pages_analyzed=1,
        )
        assert b["scoring_mode"] == "flat_small_crawl"
        assert b["components"][0]["mode"] == "flat"
        # Flat charges the weight itself, not weight x prevalence x scale.
        assert b["components"][0]["penalty"] == float(SCORING.weights.critical)

    def test_large_crawl_uses_prevalence_mode(self):
        b = compute_score_breakdown(
            _issues("missing_h1", Severity.CRITICAL, 5, pages=5),
            SCORING,
            pages_analyzed=5,
        )
        assert b["scoring_mode"] == "prevalence"
        assert b["components"][0]["mode"] == "prevalence"

    def test_threshold_boundary_is_inclusive(self):
        below = compute_score_breakdown([], SCORING, pages_analyzed=4)
        at = compute_score_breakdown([], SCORING, pages_analyzed=5)
        assert below["scoring_mode"] == "flat_small_crawl"
        assert at["scoring_mode"] == "prevalence"

    def test_one_page_critical_is_not_punished_for_sample_size(self):
        """A lone critical on a 1-page crawl must not cost prevalence-scale points."""
        b = compute_score_breakdown(
            _issues("missing_h1", Severity.CRITICAL, 1, pages=1),
            SCORING,
            pages_analyzed=1,
        )
        inflated = SCORING.weights.critical * SCORING.prevalence_scale
        assert b["total_penalty"] < inflated

    def test_flat_mode_still_does_not_stack_repeats_on_one_page(self):
        many = compute_score(
            _issues("missing_image_alt", Severity.WARNING, 60, pages=1),
            SCORING,
            pages_analyzed=1,
        )
        one = compute_score(
            _issues("missing_image_alt", Severity.WARNING, 1, pages=1),
            SCORING,
            pages_analyzed=1,
        )
        assert many == one

    def test_mode_is_explained_in_the_breakdown(self):
        b = compute_score_breakdown([], SCORING, pages_analyzed=2)
        assert "threshold" in b["scoring_mode_note"]
        assert b["min_pages_for_prevalence"] == 5


class TestPenaltyCap:
    def test_page_level_penalty_is_capped(self):
        issues = []
        for i in range(40):
            issues += _issues(f"synthetic_code_{i}", Severity.CRITICAL, 50, pages=50)
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=50)
        assert b["page_level_cap_hit"] is True
        assert b["page_level_penalty_capped"] == MAX_PAGE_LEVEL_PENALTY

    def test_score_stays_in_range(self):
        for n in (0, 1, 10, 500, 5000):
            score = compute_score(
                _issues("missing_h1", Severity.CRITICAL, n), SCORING, pages_analyzed=50
            )
            assert 0.0 <= score <= 100.0, (n, score)

    def test_clean_site_scores_100(self):
        b = compute_score_breakdown([], SCORING, pages_analyzed=50)
        assert b["score"] == 100.0
        assert b["total_penalty"] == 0.0


class TestRedirectChainIsInformational:
    def test_redirect_chain_is_registered_as_informational(self):
        assert "redirect_chain" in INFORMATIONAL_ONLY_CODES

    def test_redirect_chains_cost_nothing(self):
        issues = _issues("redirect_chain", Severity.INFO, 48, pages=48)
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=50)
        assert b["score"] == 100.0
        assert b["total_penalty"] == 0.0

    def test_redirect_chains_remain_visible_in_the_breakdown(self):
        """Must not be silently dropped — visibility was explicitly required."""
        issues = _issues("redirect_chain", Severity.INFO, 48, pages=48)
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=50)
        entry = next(c for c in b["components"] if c["code"] == "redirect_chain")
        assert entry["scored"] is False
        assert entry["scope"] == "informational"
        assert entry["count"] == 48
        assert entry["pages_affected"] == 48
        assert entry["penalty"] == 0.0
        assert "visibility" in entry["note"]
        assert b["issues_informational"] == 48

    def test_informational_issues_still_counted_in_total(self):
        issues = _issues("redirect_chain", Severity.INFO, 10, pages=10) + _issues(
            "missing_h1", Severity.CRITICAL, 5, pages=5
        )
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=20)
        assert b["issues_total"] == 15
        assert b["issues_scored"] == 5
        assert b["issues_informational"] == 10


class TestSiteLevelIssues:
    def test_site_level_issue_charged_once_not_per_page(self):
        issues = _issues("sitemap_not_checked", Severity.INFO, 1, pages=1)
        small = compute_score_breakdown(issues, SCORING, pages_analyzed=1)
        large = compute_score_breakdown(issues, SCORING, pages_analyzed=50)
        assert small["site_level_penalty"] == large["site_level_penalty"]

    def test_breakdown_explains_every_component(self):
        issues = _issues("missing_h1", Severity.CRITICAL, 3, pages=3) + _issues(
            "redirect_chain", Severity.INFO, 2, pages=2
        )
        b = compute_score_breakdown(issues, SCORING, pages_analyzed=10)
        codes = {c["code"] for c in b["components"]}
        assert codes == {"missing_h1", "redirect_chain"}
        for key in ("score", "raw_score", "total_penalty", "weights", "pages_analyzed"):
            assert key in b
