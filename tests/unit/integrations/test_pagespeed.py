"""PageSpeed Insights client tests (no live Google calls)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import PageSpeedSettings
from app.integrations.google.pagespeed import (
    PageSpeedClient,
    PageSpeedError,
    parse_pagespeed_response,
)
from app.integrations.google.pagespeed_service import PageSpeedService


def _sample_psi_payload(*, score: float = 0.42, lcp: float = 4200, cls: float = 0.25) -> dict:
    return {
        "id": "https://example.com/",
        "lighthouseResult": {
            "finalUrl": "https://example.com/",
            "categories": {"performance": {"score": score}},
            "audits": {
                "largest-contentful-paint": {
                    "numericValue": lcp,
                    "displayValue": "4.2 s",
                },
                "cumulative-layout-shift": {
                    "numericValue": cls,
                    "displayValue": "0.25",
                },
                "interaction-to-next-paint": {
                    "numericValue": 80,
                    "displayValue": "80 ms",
                },
                "total-blocking-time": {"numericValue": 300},
                "first-contentful-paint": {"numericValue": 1800},
                "speed-index": {"numericValue": 3500},
            },
        },
        "loadingExperience": {
            "overall_category": "AVERAGE",
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": {
                    "percentile": 2800,
                    "category": "AVERAGE",
                }
            },
        },
    }


class TestParsePageSpeed:
    def test_parses_lab_and_emits_issues_for_poor_vitals(self):
        settings = PageSpeedSettings()
        parsed = parse_pagespeed_response(
            _sample_psi_payload(), strategy="mobile", settings=settings
        )
        assert parsed["lab"]["performance_score"] == 42
        assert parsed["lab"]["lcp_ms"] == 4200.0
        assert parsed["field"]["overall_category"] == "AVERAGE"
        codes = {i.code for i in parsed["issues"]}
        assert "pagespeed_low_performance" in codes
        assert "pagespeed_poor_lcp" in codes
        assert "pagespeed_poor_cls" in codes
        assert "pagespeed_poor_inp" not in codes  # 80ms is good

    def test_good_vitals_produce_no_issues(self):
        settings = PageSpeedSettings()
        parsed = parse_pagespeed_response(
            _sample_psi_payload(score=0.92, lcp=1800, cls=0.05),
            strategy="mobile",
            settings=settings,
        )
        assert parsed["issues"] == []


class TestPageSpeedClient:
    def test_requires_api_key(self):
        client = PageSpeedClient(PageSpeedSettings(api_key=None))
        with pytest.raises(PageSpeedError):
            client.run("https://example.com/")

    def test_run_calls_api_and_parses(self):
        client = PageSpeedClient(PageSpeedSettings(api_key="test-key"))
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = _sample_psi_payload()
        with patch("app.integrations.google.pagespeed.requests.get", return_value=fake) as get:
            result = client.run("https://example.com/", strategy="mobile")
        assert result["lab"]["performance_score"] == 42
        assert get.call_args.kwargs["params"]["key"] == "test-key"
        assert get.call_args.kwargs["params"]["strategy"] == "mobile"

    def test_both_strategies(self):
        client = PageSpeedClient(PageSpeedSettings(api_key="k", strategy="both"))
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = _sample_psi_payload(score=0.9, lcp=1000, cls=0.01)
        with patch("app.integrations.google.pagespeed.requests.get", return_value=fake):
            out = client.analyze_url("https://example.com/")
        assert out["status"] == "ok"
        assert len(out["strategies"]) == 2


class TestPageSpeedService:
    def test_skipped_without_key(self):
        from app.config.settings import Settings

        settings = Settings(pagespeed=PageSpeedSettings(api_key=None))
        settings.pagespeed = PageSpeedSettings(api_key=None)
        service = PageSpeedService(settings)
        block, issues = service.audit_enrichment("https://example.com/")
        assert block["status"] == "skipped"
        assert issues == []

    def test_enrichment_returns_issues(self):
        from app.config.settings import Settings

        settings = Settings(pagespeed=PageSpeedSettings(api_key="k"))
        settings.pagespeed = PageSpeedSettings(api_key="k")
        service = PageSpeedService(settings)
        fake = MagicMock()
        fake.status_code = 200
        fake.json.return_value = _sample_psi_payload()
        with patch("app.integrations.google.pagespeed.requests.get", return_value=fake):
            block, issues = service.audit_enrichment("https://example.com/")
        assert block["status"] == "ok"
        assert len(issues) >= 1
        assert "issue_objects" not in block or block.get("issue_objects") == []
