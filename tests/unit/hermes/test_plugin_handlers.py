from pathlib import Path

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
        schemas.GENERATE_REPORT,
        schemas.COMPARE_AUDITS,
        schemas.LIST_SEO_HISTORY,
    ):
        assert "name" in schema
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"


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
