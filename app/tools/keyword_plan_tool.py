from __future__ import annotations

from typing import Any

from app.config.settings import get_settings
from app.services.keyword_planner import KeywordPlanner


def keyword_plan(
    url: str,
    *,
    target_keywords: list[str] | None = None,
    auth_cookie: str | None = None,
    auth_headers: dict[str, str] | None = None,
    use_authenticated_crawl: bool = False,
) -> dict[str, Any]:
    """Hermes-ready tool: where do these keywords fit on this LIVE page?

    Always fetches the URL. Never inspects the local filesystem.
    """
    planner = KeywordPlanner(settings=get_settings())
    return planner.plan(
        url,
        target_keywords=target_keywords,
        auth_cookie=auth_cookie,
        auth_headers=auth_headers,
        use_authenticated_crawl=use_authenticated_crawl,
    )
