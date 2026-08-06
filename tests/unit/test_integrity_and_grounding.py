"""Regressions for the bug round: live-page grounding, integrity, clean output."""

from __future__ import annotations

import json

from app.analyzers.recommendations import build_prescriptive_recommendations
from app.models.page import PageExtraction
from app.services.keyword_planner import analyze_keyword_placement
from app.utils.integrity import check_url_integrity
from integrations.hermes.seo_agent_plugin import handlers


def _page(**kwargs) -> PageExtraction:
    defaults = dict(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        title="Example — Read less, Live more",
        meta_description="Example turns passive learning into active learning.",
        h1=["Read less, live more."],
        h2=["From lesson to lived experience"],
        word_count=248,
        text_sample="Example helps you turn books into lived experience.",
        js_rendered=True,
    )
    defaults.update(kwargs)
    return PageExtraction(**defaults)


class TestUrlIntegrity:
    def test_exact_match_passes(self):
        result = check_url_integrity("https://example.com", ["https://example.com/"])
        assert result["ok"] and result["exact_match"]
        assert result["warning"] is None

    def test_www_and_trailing_slash_are_not_mismatches(self):
        result = check_url_integrity("https://www.example.com/", ["https://example.com"])
        assert result["ok"] and result["exact_match"]

    def test_different_site_is_flagged(self):
        result = check_url_integrity("https://example.com", ["https://other-site.com/"])
        assert result["ok"] is False
        assert "URL INTEGRITY FAILURE" in result["warning"]

    def test_redirect_to_same_host_warns_but_passes(self):
        result = check_url_integrity("https://example.com/old", ["https://example.com/new"])
        assert result["ok"] is True
        assert result["exact_match"] is False
        assert "redirected" in result["warning"]


class TestKeywordPlacementGrounding:
    def test_findings_quote_the_actual_page_copy(self):
        findings, placements = analyze_keyword_placement(_page(), ["active learning"])
        title_finding = next(f for f in findings if "title" in f["finding"])
        # Must reference the real title, not generic advice.
        assert "Example — Read less, Live more" in title_finding["finding"]
        assert placements[0]["present_in"] == ["meta_description"]
        assert "title" in placements[0]["missing_from"]

    def test_rewrites_are_concrete_for_missing_slots(self):
        _, placements = analyze_keyword_placement(_page(), ["reading app"])
        rewrites = placements[0]["rewrites"]
        assert "reading app" in rewrites["title"]["suggested"].lower()
        assert rewrites["title"]["suggested_length"] <= 60
        assert rewrites["h1"]["current"] == "Read less, live more."

    def test_no_keywords_says_so_instead_of_inventing(self):
        findings, placements = analyze_keyword_placement(_page(), [])
        assert placements == []
        assert "No target keywords were provided" in findings[0]["finding"]


class TestRecommendationQuality:
    def test_short_title_is_not_duplicated_with_its_own_h1(self):
        rec = build_prescriptive_recommendations([_page()])[0]
        suggested = rec["rewrites"]["title"]["suggested"]
        assert suggested.lower().count("read less") <= 1

    def test_no_filler_padding_in_meta(self):
        rec = build_prescriptive_recommendations([_page()])[0]
        assert "details details" not in rec["rewrites"]["meta_description"]["suggested"]

    def test_unrendered_page_blocks_copy_advice(self):
        page = _page(js_rendered=False, seo_signals={"likely_js_shell": True}, word_count=5)
        rec = build_prescriptive_recommendations([page])[0]
        assert rec["rendering_unreliable"] is True
        assert any(a["code"] == "enable_js_rendering" for a in rec["actions"])


class TestOutputHygiene:
    def test_local_paths_are_scrubbed_recursively(self):
        payload = {
            "screenshot": "file:///Users/someone/.hermes/cache/screenshots/a.png",
            "nested": {"logs": ["/Users/someone/.hermes/cache/delegation/task-0.log"]},
            "keep": "https://example.com/images/a.png",
        }
        out = json.loads(handlers._ok(payload))
        assert "/Users/" not in json.dumps(out)
        assert "a.png" in out["screenshot"]
        assert out["keep"] == "https://example.com/images/a.png"

    def test_diff_markers_are_stripped(self):
        diff = "+# SEO Report\n+\n+## Summary\n+- Score: 90"
        cleaned = handlers._strip_diff_markers(diff)
        assert cleaned.startswith("# SEO Report")
        assert "+#" not in cleaned

    def test_clean_markdown_is_left_alone(self):
        clean = "# SEO Report\n\n- Score: 90\n- Note: 1 + 1 improvements"
        assert handlers._strip_diff_markers(clean) == clean
