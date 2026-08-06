"""DataForSEO Keywords Data + Labs tests (no live API calls)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import KeywordSettings, Settings
from app.integrations.dataforseo.keywords import (
    DataForSeoClient,
    DataForSeoError,
    parse_search_volume_response,
)
from app.integrations.dataforseo.labs import (
    DataForSeoLabsClient,
    parse_bulk_difficulty_response,
    parse_related_keywords_response,
)
from app.integrations.dataforseo.service import KeywordResearchService
from app.optimizer import keyword_research as kr_mod


def _sample_volume_payload() -> dict:
    return {
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
                        "low_top_of_page_bid": 1.1,
                        "high_top_of_page_bid": 5.0,
                        "location_code": 2840,
                        "language_code": "en",
                        "monthly_searches": [],
                    }
                ],
            }
        ],
    }


def _sample_difficulty_payload() -> dict:
    return {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {"keyword": "seo audit", "keyword_difficulty": 42}
                        ]
                    }
                ],
            }
        ],
    }


def _sample_related_payload() -> dict:
    return {
        "status_code": 20000,
        "tasks": [
            {
                "status_code": 20000,
                "result": [
                    {
                        "items": [
                            {
                                "depth": 1,
                                "related_keywords": ["website seo audit"],
                                "keyword_data": {
                                    "keyword": "website seo audit",
                                    "keyword_info": {
                                        "search_volume": 720,
                                        "cpc": 4.1,
                                        "competition_level": "LOW",
                                    },
                                    "keyword_properties": {
                                        "keyword_difficulty": 28
                                    },
                                },
                            }
                        ]
                    }
                ],
            }
        ],
    }


class TestParseSearchVolume:
    def test_parses_rows(self):
        rows = parse_search_volume_response(_sample_volume_payload())
        assert len(rows) == 1
        assert rows[0]["keyword"] == "seo audit"
        assert rows[0]["search_volume"] == 2400
        assert rows[0]["cpc"] == 3.2

    def test_raises_on_top_level_error(self):
        with pytest.raises(DataForSeoError):
            parse_search_volume_response(
                {"status_code": 40100, "status_message": "Unauthorized"}
            )


class TestParseLabs:
    def test_parse_difficulty(self):
        mapping = parse_bulk_difficulty_response(_sample_difficulty_payload())
        assert mapping["seo audit"] == 42

    def test_parse_related(self):
        rows = parse_related_keywords_response(_sample_related_payload())
        assert rows[0]["keyword"] == "website seo audit"
        assert rows[0]["keyword_difficulty"] == 28
        assert rows[0]["search_volume"] == 720


class TestDataForSeoClient:
    def test_requires_credentials(self):
        client = DataForSeoClient(KeywordSettings(provider="dataforseo"))
        assert client.is_configured() is False

    def test_search_volume_posts(self):
        client = DataForSeoClient(
            KeywordSettings(
                provider="dataforseo",
                login="user@example.com",
                password="secret",
            )
        )
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = _sample_volume_payload()
        with patch(
            "app.integrations.dataforseo.keywords.requests.post", return_value=fake
        ) as post:
            rows = client.search_volume(["seo audit", "seo audit"])
        assert len(rows) == 1
        assert post.call_args.kwargs["auth"] == ("user@example.com", "secret")
        body = post.call_args.kwargs["json"]
        assert body[0]["keywords"] == ["seo audit"]


class TestLabsClient:
    def test_difficulty_and_related(self):
        client = DataForSeoLabsClient(
            KeywordSettings(provider="dataforseo", login="u", password="p")
        )

        def _post(url, *args, **kwargs):  # noqa: ANN001
            fake = MagicMock(status_code=200)
            if "bulk_keyword_difficulty" in url:
                fake.json.return_value = _sample_difficulty_payload()
            else:
                fake.json.return_value = _sample_related_payload()
            return fake

        with patch("requests.post", side_effect=_post):
            mapping = client.bulk_keyword_difficulty(["seo audit"])
            related = client.related_keywords("seo audit")
        assert mapping["seo audit"] == 42
        assert related[0]["keyword"] == "website seo audit"


class TestKeywordResearchService:
    def test_unavailable_without_config(self):
        settings = Settings(keywords=KeywordSettings(provider=None))
        settings.keywords = KeywordSettings(provider=None)
        out = KeywordResearchService(settings).research(["seo"])
        assert out["status"] == "unavailable"
        assert out["is_real_research"] is False

    def test_ok_with_volume_and_labs(self):
        settings = Settings(
            keywords=KeywordSettings(
                provider="dataforseo",
                login="u",
                password="p",
                labs_enabled=True,
                include_related_in_research=True,
            )
        )
        settings.keywords = KeywordSettings(
            provider="dataforseo",
            login="u",
            password="p",
            labs_enabled=True,
            include_related_in_research=True,
        )
        service = KeywordResearchService(settings)

        def _post(url, *args, **kwargs):  # noqa: ANN001
            fake = MagicMock(status_code=200)
            if "search_volume" in url:
                fake.json.return_value = _sample_volume_payload()
            elif "bulk_keyword_difficulty" in url:
                fake.json.return_value = _sample_difficulty_payload()
            elif "related_keywords" in url:
                fake.json.return_value = _sample_related_payload()
            else:
                raise AssertionError(f"unexpected url {url}")
            return fake

        with patch("requests.post", side_effect=_post):
            out = service.research(["seo audit"])
        assert out["status"] == "ok"
        assert out["is_real_research"] is True
        assert out["keywords"][0]["search_volume"] == 2400
        assert out["keywords"][0]["keyword_difficulty"] == 42
        assert out["related"][0]["keyword"] == "website seo audit"


class TestNormalizeCallerKeywords:
    def test_researched_when_provider_works(self, monkeypatch):
        monkeypatch.setenv("KEYWORD_API_PROVIDER", "dataforseo")
        monkeypatch.setenv("KEYWORD_API_LOGIN", "u")
        monkeypatch.setenv("KEYWORD_API_PASSWORD", "p")
        monkeypatch.setenv("KEYWORD_LABS_ENABLED", "false")
        from app.config import settings as settings_module

        settings_module.get_settings.cache_clear()

        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = _sample_volume_payload()
        with patch(
            "app.integrations.dataforseo.keywords.requests.post", return_value=fake
        ):
            out = kr_mod.normalize_caller_keywords(["seo audit"])
        assert out["status"] == "researched"
        assert out["is_real_research"] is True
        assert out["metrics"][0]["search_volume"] == 2400
        settings_module.get_settings.cache_clear()

    def test_unavailable_without_env(self, monkeypatch):
        monkeypatch.setenv("KEYWORD_API_PROVIDER", "")
        monkeypatch.setenv("KEYWORD_API_LOGIN", "")
        monkeypatch.setenv("KEYWORD_API_PASSWORD", "")
        from app.config import settings as settings_module

        settings_module.get_settings.cache_clear()
        out = kr_mod.normalize_caller_keywords(["seo"])
        assert out["is_real_research"] is False
        assert out["status"] == "caller_provided_not_researched"
        settings_module.get_settings.cache_clear()
