from __future__ import annotations

from app.config.settings import get_settings
from app.models.optimization import OptimizationResult
from app.services.optimizer_service import OptimizerService


def optimize_page(
    url: str,
    *,
    target_keywords: list[str] | None = None,
    auth_cookie: str | None = None,
    auth_headers: dict[str, str] | None = None,
    use_authenticated_crawl: bool = False,
) -> OptimizationResult:
    """Hermes-ready tool: generate AI SEO suggestions for a single page."""
    settings = get_settings()
    return OptimizerService(settings=settings).optimize_page(
        url,
        target_keywords=target_keywords,
        auth_cookie=auth_cookie,
        auth_headers=auth_headers,
        use_authenticated_crawl=use_authenticated_crawl,
    )
