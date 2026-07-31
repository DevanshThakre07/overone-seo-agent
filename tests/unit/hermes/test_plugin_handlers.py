from pathlib import Path

import responses

from integrations.hermes.seo_agent_plugin import handlers
from integrations.hermes.seo_agent_plugin import schemas

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_schemas_have_required_shape():
    for schema in (
        schemas.AUDIT_SITE,
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
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()

    html = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/", body=html, status=200)
    responses.add(responses.GET, "https://example.com/sample", body=html, status=200)
    responses.add(responses.GET, "https://example.com/about", body=html, status=200)

    raw = handlers.handle_audit_site(
        {"url": "https://example.com/", "max_pages": 2, "save": True}
    )
    assert '"audit_id"' in raw
    assert '"score"' in raw
    assert '"error"' not in raw or '"audit_id"' in raw
