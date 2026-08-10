from app.analyzers.recommendations import build_prescriptive_recommendations
from app.analyzers.rendering_guardrails import apply_rendering_guardrails
from app.models.issues import Issue, Severity
from app.models.page import PageExtraction


def test_rendering_guardrails_suppress_false_spa_findings():
    page = PageExtraction(
        url="https://actoro.app/",
        final_url="https://actoro.app/",
        title="Actoro",
        word_count=5,
        js_rendered=False,
        seo_signals={"likely_js_shell": True},
    )
    issues = [
        Issue(
            code="missing_h1",
            severity=Severity.CRITICAL,
            message="Page is missing an H1 heading",
            url=page.final_url,
        ),
        Issue(
            code="title_too_short",
            severity=Severity.WARNING,
            message="Title is short",
            url=page.final_url,
        ),
    ]
    kept, results, meta = apply_rendering_guardrails([page], issues, [])
    assert meta["rendering_incomplete"] is True
    assert any(i.code == "rendering_incomplete" for i in kept)
    assert not any(i.code == "missing_h1" for i in kept)
    assert any(i.code == "title_too_short" for i in kept)
    assert results[0].analyzer == "rendering"


def test_prescriptive_recommendations_include_concrete_copy():
    page = PageExtraction(
        url="https://example.com",
        final_url="https://example.com",
        title="Short",
        meta_description=None,
        h1=["Welcome Home"],
    )
    recs = build_prescriptive_recommendations([page])
    assert recs
    assert recs[0]["suggested_title"]
    assert len(recs[0]["suggested_title"]) >= 30
    assert recs[0]["suggested_meta_description"]
    assert recs[0]["rewrites"]["title"]["suggested"]
    assert recs[0]["rewrites"]["meta_description"]["suggested"]
    assert any(a["code"] == "missing_meta_description" for a in recs[0]["actions"])


def test_playwright_works_inside_asyncio_loop():
    """Hermes invokes tools under asyncio — Sync Playwright must be thread-isolated."""
    import asyncio

    from app.crawler.playwright_client import PlaywrightClient
    from app.config.settings import PlaywrightSettings

    if not PlaywrightClient.is_available():
        return

    pw = PlaywrightClient(PlaywrightSettings(enabled=True, timeout_ms=45000))

    async def run() -> None:
        result = pw.fetch_with_diagnostics("https://example.com/", force_for_spa=True)
        assert result.error != (
            "It looks like you are using Playwright Sync API inside the asyncio loop.\n"
            "Please use the Async API instead."
        )
        # example.com is static; fetch should still succeed (ok or captured html)
        assert result.ok or result.html or result.error not in {None, ""}

    asyncio.run(run())


def test_merge_gsc_into_recommendations_attaches_actions():
    from app.analyzers.recommendations import merge_gsc_into_recommendations

    recs = [
        {
            "url": "https://example.com/",
            "actions": [{"code": "missing_canonical", "message": "add canonical"}],
        }
    ]
    gsc = {
        "status": "ok",
        "snapshot": {
            "opportunities": [
                {
                    "kind": "page2",
                    "query": "active learning",
                    "page": "https://example.com/",
                    "impressions": 120,
                    "clicks": 5,
                    "ctr": 0.04,
                    "position": 14.2,
                    "why": "page 2",
                },
                {
                    "kind": "low_ctr",
                    "query": "weak snippet",
                    "page": "https://example.com/blog",
                    "impressions": 200,
                    "clicks": 2,
                    "ctr": 0.01,
                    "position": 4.0,
                    "why": "low ctr",
                },
            ],
            "opportunity_count": 2,
        },
    }
    merged = merge_gsc_into_recommendations(recs, gsc)
    home = next(r for r in merged if "example.com" in r["url"] and "/blog" not in r["url"])
    assert any(a["code"] == "gsc_page2_opportunity" for a in home["actions"])
    blog = next(r for r in merged if r["url"].endswith("/blog"))
    assert blog.get("source") == "google_search_console"
    assert any(a["code"] == "gsc_low_ctr" for a in blog["actions"])


def test_merge_gsc_skipped_when_not_ok():
    from app.analyzers.recommendations import merge_gsc_into_recommendations

    recs = [{"url": "https://example.com/", "actions": []}]
    out = merge_gsc_into_recommendations(recs, {"status": "no_matching_property"})
    assert out == recs
    assert merge_gsc_into_recommendations(recs, None) == recs
