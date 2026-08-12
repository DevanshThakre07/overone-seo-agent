"""PP-8: recommendations must cite evidence and must not contradict page data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analyzers.recommendations import (
    build_prescriptive_recommendations,
    merge_gsc_into_recommendations,
)
from app.analyzers.schema_analyzer import _suggested_schema_types
from app.models.page import PageExtraction

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "rec_accuracy"


def _load_page(name: str) -> PageExtraction:
    data = json.loads((FIXTURES / name).read_text())
    return PageExtraction.model_validate(data)


def _assert_action_evidence(action: dict) -> None:
    evidence = action.get("evidence")
    assert isinstance(evidence, dict), f"{action.get('code')} missing evidence"
    assert evidence.get("url"), f"{action.get('code')} evidence.url empty"
    assert "field" in evidence, f"{action.get('code')} evidence.field missing"
    assert "current_value" in evidence
    assert "suggested_value" in evidence


@pytest.mark.parametrize(
    "fixture",
    ["actoro_home.json", "privacy_page.json", "complete_page.json"],
)
def test_every_action_has_evidence(fixture: str):
    page = _load_page(fixture)
    recs = build_prescriptive_recommendations([page])
    assert len(recs) == 1
    for action in recs[0]["actions"]:
        _assert_action_evidence(action)


def test_actoro_home_does_not_claim_missing_present_fields():
    page = _load_page("actoro_home.json")
    rec = build_prescriptive_recommendations([page])[0]
    codes = {a["code"] for a in rec["actions"]}

    assert "missing_title" not in codes
    assert "missing_h1" not in codes
    assert "missing_canonical" not in codes
    assert "missing_meta_description" not in codes

    # Short title/meta should rewrite or advise — evidence must match live values.
    title_actions = [a for a in rec["actions"] if a["evidence"]["field"] == "title"]
    assert title_actions
    assert all(a["evidence"]["current_value"] == "Actoro" for a in title_actions)

    meta_actions = [a for a in rec["actions"] if a["evidence"]["field"] == "meta_description"]
    assert meta_actions
    assert all(
        a["evidence"]["current_value"] == "Read less, live more." for a in meta_actions
    )

    assert any(a["code"] == "missing_image_alt" for a in rec["actions"])
    alt = next(a for a in rec["actions"] if a["code"] == "missing_image_alt")
    assert alt["evidence"]["url"] == "https://actoro.app/"
    assert "hero.png" in (alt.get("src") or "")


def test_privacy_page_avoids_homepage_marketing_copy():
    page = _load_page("privacy_page.json")
    rec = build_prescriptive_recommendations([page])[0]
    assert rec["page_kind"] == "privacy"

    suggested_meta = (rec.get("suggested_meta_description") or "").lower()
    assert "learn what it offers" not in suggested_meta
    assert "get started today" not in suggested_meta
    assert "privacy" in suggested_meta or "personal data" in suggested_meta

    codes = {a["code"] for a in rec["actions"]}
    assert "missing_meta_description" in codes
    assert "missing_canonical" in codes
    meta = next(a for a in rec["actions"] if a["code"] == "missing_meta_description")
    assert meta["evidence"]["current_value"] is None
    assert "personal data" in (meta["evidence"]["suggested_value"] or "").lower() or (
        "privacy" in (meta["evidence"]["suggested_value"] or "").lower()
    )


def test_complete_page_has_no_missing_field_contradictions():
    page = _load_page("complete_page.json")
    rec = build_prescriptive_recommendations([page])[0]
    codes = {a["code"] for a in rec["actions"]}

    for forbidden in (
        "missing_title",
        "missing_meta_description",
        "missing_h1",
        "missing_canonical",
        "missing_image_alt",
        "multiple_h1",
    ):
        assert forbidden not in codes

    # Title/meta already in band — evidence current must equal page, no invented missings.
    assert rec["current"]["title"] == page.title
    assert rec["current"]["meta_description"] == page.meta_description
    assert rec["current"]["h1"] == page.h1[0]


def test_js_shell_unreliable_skips_on_page_rewrites():
    page = PageExtraction(
        url="https://actoro.app/",
        final_url="https://actoro.app/",
        title="Shell",
        meta_description=None,
        h1=[],
        js_rendered=False,
        seo_signals={"likely_js_shell": True},
    )
    rec = build_prescriptive_recommendations([page])[0]
    assert rec["rendering_unreliable"] is True
    assert rec["suggested_title"] is None
    codes = {a["code"] for a in rec["actions"]}
    assert codes == {"enable_js_rendering"}
    _assert_action_evidence(rec["actions"][0])


def test_evidence_url_matches_recommendation_page():
    pages = [
        _load_page("actoro_home.json"),
        _load_page("privacy_page.json"),
        _load_page("complete_page.json"),
    ]
    for rec in build_prescriptive_recommendations(pages):
        for action in rec["actions"]:
            assert action["evidence"]["url"] == rec["url"]


def test_gsc_merge_actions_include_evidence():
    recs = build_prescriptive_recommendations([_load_page("complete_page.json")])
    gsc = {
        "status": "ok",
        "snapshot": {
            "opportunities": [
                {
                    "kind": "low_ctr",
                    "query": "sample seo page",
                    "page": "https://example.com/sample",
                    "impressions": 200,
                    "clicks": 2,
                    "ctr": 0.01,
                    "position": 4.0,
                    "why": "low ctr",
                }
            ],
            "opportunity_count": 1,
        },
    }
    merged = merge_gsc_into_recommendations(recs, gsc)
    page_rec = merged[0]
    gsc_actions = [a for a in page_rec["actions"] if a.get("source") == "google_search_console"]
    assert gsc_actions
    for action in gsc_actions:
        _assert_action_evidence(action)
        assert action["evidence"]["field"] == "gsc_query"


@pytest.mark.parametrize(
    "url,title,h1,is_seed,expect_kind,expect_types",
    [
        ("https://actoro.app/", "Actoro", "Read less", True, "home", ["Organization", "WebSite"]),
        ("https://actoro.app/privacy", "Privacy", "Privacy Policy", False, "legal", ["WebPage"]),
        ("https://example.com/blog/post", "Post", "Hello", False, "article", ["Article", "BlogPosting"]),
    ],
)
def test_schema_advisor_by_page_kind(url, title, h1, is_seed, expect_kind, expect_types):
    suggested = _suggested_schema_types(url, title=title, h1=h1, is_seed=is_seed)
    assert suggested["kind"] == expect_kind
    assert suggested["types"] == expect_types
    # Legal pages must not be told to add Product/FAQ.
    if expect_kind == "legal":
        assert "Product" not in suggested["types"]
        assert "FAQPage" not in suggested["types"]
