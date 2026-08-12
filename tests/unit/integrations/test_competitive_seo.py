"""Phase 2 competitive SEO — SERP / rank / backlinks (mocked, no live calls)."""

from __future__ import annotations

from unittest.mock import patch

from app.config.settings import KeywordSettings, Settings
from app.integrations.dataforseo.backlinks import (
    normalize_backlink_target,
    parse_referring_domains_response,
    parse_summary_response,
)
from app.integrations.dataforseo.competitive import CompetitiveSeoService
from app.integrations.dataforseo.serp import (
    find_domain_rank,
    normalize_domain,
    parse_serp_response,
)


def _serp_payload() -> dict:
    return {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "keyword": "rare books",
                        "location_code": 2840,
                        "language_code": "en",
                        "device": "desktop",
                        "items_count": 3,
                        "items": [
                            {
                                "type": "organic",
                                "rank_group": 1,
                                "rank_absolute": 1,
                                "domain": "www.competitor.com",
                                "url": "https://www.competitor.com/books",
                                "title": "Competitor Books",
                                "description": "A",
                            },
                            {
                                "type": "organic",
                                "rank_group": 2,
                                "rank_absolute": 2,
                                "domain": "bookasto.com",
                                "url": "https://bookasto.com/",
                                "title": "Bookasto",
                                "description": "B",
                            },
                            {
                                "type": "paid",
                                "rank_group": 1,
                                "domain": "ads.example",
                                "url": "https://ads.example/",
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_parse_serp_keeps_organic_only():
    parsed = parse_serp_response(_serp_payload())
    assert parsed["organic_count"] == 2
    assert parsed["organic"][0]["domain"] == "www.competitor.com"
    assert parsed["organic"][1]["domain"] == "bookasto.com"


def test_find_domain_rank():
    organic = parse_serp_response(_serp_payload())["organic"]
    hit = find_domain_rank(organic, "https://www.bookasto.com/about")
    assert hit["found"] is True
    assert hit["position"] == 2
    miss = find_domain_rank(organic, "missing.example")
    assert miss["found"] is False


def test_normalize_domain():
    assert normalize_domain("https://www.Bookasto.com/path") == "bookasto.com"
    assert normalize_backlink_target("https://bookasto.com/page") == (
        "https://bookasto.com/page"
    )
    assert normalize_backlink_target("www.bookasto.com") == "bookasto.com"


def test_parse_backlinks_summary():
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "bookasto.com",
                        "rank": 120,
                        "backlinks": 42,
                        "referring_domains": 18,
                        "referring_main_domains": 15,
                        "referring_pages": 40,
                    }
                ],
            }
        ],
    }
    parsed = parse_summary_response(payload)
    assert parsed["backlinks"] == 42
    assert parsed["referring_domains"] == 18


def test_parse_referring_domains():
    payload = {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "target": "bookasto.com",
                        "total_count": 2,
                        "items": [
                            {
                                "domain": "news.example",
                                "rank": 200,
                                "backlinks": 5,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    parsed = parse_referring_domains_response(payload)
    assert parsed["referring_domains"][0]["domain"] == "news.example"


def test_competitive_check_rank_mocked():
    settings = Settings(
        keywords=KeywordSettings(
            enabled=True,
            provider="dataforseo",
            login="u",
            password="p",
        )
    )
    service = CompetitiveSeoService(settings)
    with patch.object(service.serp, "organic_live", return_value=parse_serp_response(_serp_payload()) | {"depth": 10, "source": "test"}):
        result = service.check_rank("rare books", "bookasto.com")
    assert result["status"] == "ok"
    assert result["rank"]["found"] is True
    assert result["rank"]["position"] == 2


def test_competitive_unavailable_without_creds():
    settings = Settings(keywords=KeywordSettings(provider=None))
    service = CompetitiveSeoService(settings)
    assert service.check_serp("x")["status"] == "unavailable"
    assert service.check_backlinks("example.com")["status"] == "unavailable"


def test_audit_serp_requires_keywords():
    settings = Settings(
        keywords=KeywordSettings(
            enabled=True, provider="dataforseo", login="u", password="p"
        )
    )
    service = CompetitiveSeoService(settings)
    skipped = service.audit_serp_enrichment("https://bookasto.com/", [])
    assert skipped["status"] == "skipped"


def test_audit_serp_aggregate_error_when_all_checks_fail(monkeypatch):
    settings = Settings(
        keywords=KeywordSettings(
            enabled=True, provider="dataforseo", login="u", password="p"
        )
    )
    service = CompetitiveSeoService(settings)

    def boom(keyword, target, **kwargs):
        return {
            "status": "error",
            "keyword": keyword,
            "rank": None,
            "message": "402 Payment Required",
        }

    monkeypatch.setattr(service, "check_rank", boom)
    out = service.audit_serp_enrichment(
        "https://bookasto.com/", ["seo", "books"]
    )
    assert out["status"] == "payment_required"
    assert out["failed_count"] == 2
    assert out["ranked_count"] == 0
    assert "ok" != out["status"]
