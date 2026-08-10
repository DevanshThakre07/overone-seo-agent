"""Authenticated crawl — read-only, in-memory, opt-in."""

from __future__ import annotations

from app.crawler.auth import (
    CrawlAuth,
    auth_policy_block,
    build_crawl_auth,
    detect_login_wall,
)
from app.crawler.client import HttpClient


def test_detect_login_wall_password_form():
    html = """
    <html><head><title>Sign in</title></head>
    <body><form action="/login"><input type="password" name="pw"></form></body></html>
    """
    wall = detect_login_wall(
        url="https://example.com/app",
        final_url="https://example.com/login",
        status_code=200,
        html=html,
    )
    assert wall["requires_login"] is True
    assert "password_input" in wall["signals"] or "login_path" in wall["signals"]


def test_detect_login_wall_public_page():
    html = "<html><head><title>Welcome</title></head><body><h1>Hello</h1><p>Public</p></body></html>"
    wall = detect_login_wall(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        html=html,
    )
    assert wall["requires_login"] is False


def test_credentials_ignored_without_opt_in():
    auth = build_crawl_auth(auth_cookie="session=abc")
    assert auth is not None
    block = auth_policy_block(
        auth=auth,
        use_authenticated_crawl=False,
        login_wall={"requires_login": True, "message": "needs login"},
        credentials_used=False,
    )
    assert block["credentials_supplied"] is True
    assert block["credentials_used"] is False
    assert block["credentials_persisted"] is False
    assert "session=abc" not in str(block)
    assert "NOT used" in (block["message"] or "")


def test_opt_in_uses_credentials_flag():
    auth = CrawlAuth(cookie="token=xyz")
    block = auth_policy_block(
        auth=auth,
        use_authenticated_crawl=True,
        login_wall={"requires_login": True},
        credentials_used=True,
    )
    assert block["mode"] == "authenticated"
    assert block["read_only"] is True
    assert set(block["methods_allowed"]) == {"GET", "HEAD"}
    assert "xyz" not in str(block)


def test_http_client_has_no_post_method():
    client = HttpClient("UA", 5.0, 3, auth=CrawlAuth(cookie="a=1"))
    assert hasattr(client, "get")
    assert hasattr(client, "head")
    assert not hasattr(client, "post")
    assert "Cookie" in client.session.headers
    assert client.session.headers["Cookie"] == "a=1"
    client.close()


def test_redacted_summary_never_leaks_cookie_value():
    auth = CrawlAuth(cookie="secret=super-secret-value", headers={"Authorization": "Bearer tok"})
    summary = auth.redacted_summary()
    assert summary["credentials_supplied"] is True
    assert "super-secret-value" not in str(summary)
    assert "Bearer tok" not in str(summary)
    assert summary["storage"] == "memory_per_request"
