from unittest.mock import MagicMock

from app.tools import gsc_tool


def test_gsc_list_sites_ok(monkeypatch):
    service = MagicMock()
    service.list_sites.return_value = {
        "account_id": "acct",
        "sites": [{"site_url": "sc-domain:example.com", "permission_level": "siteOwner"}],
        "count": 1,
    }
    monkeypatch.setattr(gsc_tool, "_service", lambda: service)

    result = gsc_tool.gsc_list_sites("acct")
    assert result["status"] == "ok"
    assert result["count"] == 1
    service.list_sites.assert_called_once_with("acct")


def test_gsc_performance_requires_site(monkeypatch):
    result = gsc_tool.gsc_performance("acct", "")
    assert result["status"] == "error"
    assert "site_url" in result["message"]


def test_gsc_status_missing_account():
    result = gsc_tool.gsc_status("")
    assert result["status"] == "error"
