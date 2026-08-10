import json
from pathlib import Path
from unittest.mock import MagicMock

import responses

from integrations.hermes.seo_agent_plugin import handlers
from integrations.hermes.seo_agent_plugin import schemas

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_schemas_have_required_shape():
    for schema in (
        schemas.AUDIT_SITE,
        schemas.CHECK_PAGESPEED,
        schemas.RESEARCH_KEYWORDS,
        schemas.OPTIMIZE_PAGE,
        schemas.KEYWORD_PLAN,
        schemas.GENERATE_REPORT,
        schemas.COMPARE_AUDITS,
        schemas.LIST_SEO_HISTORY,
        schemas.GSC_STATUS,
        schemas.GSC_SITES,
        schemas.GSC_PERFORMANCE,
    ):
        assert "name" in schema
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"


def test_auth_headers_on_crawl_schemas():
    for schema in (schemas.AUDIT_SITE, schemas.OPTIMIZE_PAGE, schemas.KEYWORD_PLAN):
        props = schema["parameters"]["properties"]
        assert "auth_headers" in props
        assert props["auth_headers"]["type"] == "object"
        assert "auth_cookie" in props
        assert "use_authenticated_crawl" in props


def test_check_seo_available():
    assert handlers._check_seo_available() is True


@responses.activate
def test_handle_audit_site_returns_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SEO_STORAGE_PATH", str(tmp_path / "h.db"))
    monkeypatch.delenv("GOOGLE_PAGESPEED_API_KEY", raising=False)
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()

    html = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/", body=html, status=200)
    responses.add(responses.GET, "https://example.com/sample", body=html, status=200)
    responses.add(responses.GET, "https://example.com/about", body=html, status=200)

    raw = handlers.handle_audit_site(
        {
            "url": "https://example.com/",
            "max_pages": 2,
            "save": True,
            "pagespeed": False,
        }
    )
    assert '"audit_id"' in raw
    assert '"score"' in raw
    assert '"pagespeed"' in raw
    assert '"error"' not in raw or '"audit_id"' in raw


@responses.activate
def test_handle_check_pagespeed_returns_highlights(monkeypatch):
    monkeypatch.setenv("GOOGLE_PAGESPEED_API_KEY", "test-key")
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()

    payload = {
        "id": "https://example.com/",
        "lighthouseResult": {
            "finalUrl": "https://example.com/",
            "categories": {"performance": {"score": 0.39}},
            "audits": {
                "largest-contentful-paint": {
                    "numericValue": 4200,
                    "displayValue": "4.2 s",
                },
                "cumulative-layout-shift": {
                    "numericValue": 0.01,
                    "displayValue": "0.01",
                },
                "interaction-to-next-paint": {
                    "numericValue": 80,
                    "displayValue": "80 ms",
                },
                "total-blocking-time": {"numericValue": 100},
                "first-contentful-paint": {"numericValue": 1200},
                "speed-index": {"numericValue": 2000},
            },
        },
        "loadingExperience": {"overall_category": "AVERAGE", "metrics": {}},
    }
    responses.add(
        responses.GET,
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
        json=payload,
        status=200,
    )

    raw = handlers.handle_check_pagespeed(
        {"url": "https://example.com/", "strategy": "mobile"}
    )
    assert '"status": "ok"' in raw or '"status":"ok"' in raw
    assert '"highlights"' in raw
    assert '"performance_score"' in raw
    assert '"error"' not in raw or '"status"' in raw

    settings_module.get_settings.cache_clear()


@responses.activate
def test_handle_research_keywords(monkeypatch):
    monkeypatch.setenv("KEYWORD_API_PROVIDER", "dataforseo")
    monkeypatch.setenv("KEYWORD_API_LOGIN", "u")
    monkeypatch.setenv("KEYWORD_API_PASSWORD", "p")
    monkeypatch.setenv("KEYWORD_LABS_ENABLED", "false")
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()

    responses.add(
        responses.POST,
        "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
        json={
            "status_code": 20000,
            "status_message": "Ok.",
            "tasks": [
                {
                    "status_code": 20000,
                    "result": [
                        {
                            "keyword": "seo audit",
                            "search_volume": 2400,
                            "competition": "MEDIUM",
                            "competition_index": 45,
                            "cpc": 3.2,
                            "location_code": 2840,
                            "language_code": "en",
                            "monthly_searches": [],
                        }
                    ],
                }
            ],
        },
        status=200,
    )

    raw = handlers.handle_research_keywords({"keywords": "seo audit"})
    assert '"status": "ok"' in raw or '"status":"ok"' in raw
    assert '"is_real_research": true' in raw or '"is_real_research":true' in raw
    assert "2400" in raw
    settings_module.get_settings.cache_clear()


def test_handle_audit_site_passes_auth_headers(monkeypatch):
    captured: dict = {}

    def fake_audit_site(url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        audit = MagicMock()
        audit.audit_id = "a1"
        audit.seed_url = url
        audit.score = 80
        audit.pages = []
        audit.issues = []
        audit.analyzer_results = []
        audit.diff = None
        audit.optimization = None
        audit.summary = {
            "seo_metrics": {},
            "score_status": "final",
            "severity": {},
            "pagespeed": {"status": "skipped"},
            "google_search_console": {"status": "skipped"},
            "recommendations": [],
            "pages": 0,
            "issues": 0,
            "analyzers_run": [],
            "raw_score": 80,
            "crawl_auth": {
                "authenticated": True,
                "cookie_present": False,
                "extra_header_names": ["Authorization"],
            },
        }
        return audit

    monkeypatch.setattr("app.tools.audit_tool.audit_site", fake_audit_site)

    secret = "Bearer super-secret-token"
    raw = handlers.handle_audit_site(
        {
            "url": "https://example.com/",
            "auth_headers": {"Authorization": secret},
            "use_authenticated_crawl": True,
            "pagespeed": False,
            "save": False,
        }
    )
    assert captured.get("auth_headers") == {"Authorization": secret}
    assert captured.get("use_authenticated_crawl") is True
    assert secret not in raw
    payload = json.loads(raw)
    assert payload["crawl_auth"]["extra_header_names"] == ["Authorization"]


def test_handle_gsc_sites(monkeypatch):
    monkeypatch.setattr(
        "app.tools.gsc_tool.gsc_list_sites",
        lambda account_id: {
            "status": "ok",
            "account_id": account_id,
            "sites": [
                {
                    "site_url": "sc-domain:bookasto.com",
                    "permission_level": "siteOwner",
                }
            ],
            "count": 1,
        },
    )
    raw = handlers.handle_gsc_sites({"account_id": "bookasto"})
    payload = json.loads(raw)
    assert payload["status"] == "ok"
    assert payload["sites"][0]["site_url"] == "sc-domain:bookasto.com"
    assert payload["delivery"] == "inline_json"


def test_handle_gsc_performance(monkeypatch):
    monkeypatch.setattr(
        "app.tools.gsc_tool.gsc_performance",
        lambda account_id, site_url, **kwargs: {
            "status": "ok",
            "account_id": account_id,
            "site_url": site_url,
            "top_queries": [{"query": "books", "clicks": 10}],
            "opportunities": [
                {"kind": "page2", "query": "rare books", "position": 12}
            ],
            "opportunity_count": 1,
        },
    )
    raw = handlers.handle_gsc_performance(
        {
            "account_id": "bookasto",
            "site_url": "sc-domain:bookasto.com",
            "days": 28,
        }
    )
    payload = json.loads(raw)
    assert payload["status"] == "ok"
    assert payload["opportunity_count"] == 1
    assert payload["top_queries"][0]["query"] == "books"


def test_handle_gsc_status(monkeypatch):
    monkeypatch.setattr(
        "app.tools.gsc_tool.gsc_status",
        lambda account_id: {
            "status": "ok",
            "configured": True,
            "connected": True,
            "account_id": account_id,
            "email": "owner@example.com",
        },
    )
    raw = handlers.handle_gsc_status({"account_id": "bookasto"})
    payload = json.loads(raw)
    assert payload["connected"] is True
    assert "owner@example.com" in raw


def test_handle_check_serp(monkeypatch):
    monkeypatch.setattr(
        "app.tools.serp_tool.check_serp",
        lambda keyword, **kwargs: {
            "status": "ok",
            "keyword": keyword,
            "organic": [{"rank_group": 1, "domain": "a.com", "title": "A"}],
            "organic_count": 1,
        },
    )
    raw = handlers.handle_check_serp({"keyword": "rare books"})
    payload = json.loads(raw)
    assert payload["status"] == "ok"
    assert payload["organic_count"] == 1


def test_handle_check_rank(monkeypatch):
    monkeypatch.setattr(
        "app.tools.serp_tool.check_rank",
        lambda keyword, target, **kwargs: {
            "status": "ok",
            "keyword": keyword,
            "rank": {"found": True, "position": 3, "target": target},
        },
    )
    raw = handlers.handle_check_rank(
        {"keyword": "rare books", "target": "bookasto.com"}
    )
    payload = json.loads(raw)
    assert payload["rank"]["position"] == 3


def test_handle_check_backlinks(monkeypatch):
    monkeypatch.setattr(
        "app.tools.backlinks_tool.check_backlinks",
        lambda target, **kwargs: {
            "status": "ok",
            "target": target,
            "summary": {"backlinks": 10, "referring_domains": 4},
            "top_referring_domains": [{"domain": "news.example"}],
        },
    )
    raw = handlers.handle_check_backlinks({"target": "bookasto.com"})
    payload = json.loads(raw)
    assert payload["summary"]["backlinks"] == 10
