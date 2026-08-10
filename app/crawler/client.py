"""HTTP client built on Requests — GET/HEAD only (read-only crawl)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests
from requests import Response

if TYPE_CHECKING:
    from app.crawler.auth import CrawlAuth


@dataclass
class FetchResponse:
    url: str
    final_url: str
    status_code: int
    text: str
    content_length: int
    history: list[tuple[str, int]]
    elapsed_ms: float
    error: str | None = None


class HttpClient:
    """Read-only HTTP client. Intentionally exposes only GET and HEAD."""

    def __init__(
        self,
        user_agent: str,
        timeout: float,
        max_redirects: int,
        auth: CrawlAuth | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if auth and auth.configured:
            # Cookie / auth headers for this in-memory session only.
            self.session.headers.update(auth.http_headers())
        self.session.max_redirects = max_redirects
        # Defense: never allow callers to POST via this session accidentally.
        self._read_only = True

    def get(self, url: str, *, stream: bool = False) -> FetchResponse:
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            return self._to_fetch(response, requested_url=url)
        except requests.RequestException as exc:
            return FetchResponse(
                url=url,
                final_url=url,
                status_code=0,
                text="",
                content_length=0,
                history=[],
                elapsed_ms=0.0,
                error=str(exc),
            )

    def head(self, url: str) -> FetchResponse:
        try:
            response = self.session.head(
                url, timeout=self.timeout, allow_redirects=True
            )
            # Some servers reject HEAD — fall back to GET
            if response.status_code >= 400 and response.status_code != 404:
                response = self.session.get(
                    url, timeout=self.timeout, allow_redirects=True, stream=True
                )
                response.close()
            return self._to_fetch(response, requested_url=url, include_body=False)
        except requests.RequestException as exc:
            return FetchResponse(
                url=url,
                final_url=url,
                status_code=0,
                text="",
                content_length=0,
                history=[],
                elapsed_ms=0.0,
                error=str(exc),
            )

    def _to_fetch(
        self,
        response: Response,
        *,
        requested_url: str,
        include_body: bool = True,
    ) -> FetchResponse:
        history = [(h.url, h.status_code) for h in response.history]
        text = response.text if include_body else ""
        # Prefer actual downloaded body size for SEO page-size metrics.
        body_len = len(response.content or b"") if include_body else 0
        header_len = 0
        try:
            header_len = int(response.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            header_len = 0
        content_length = body_len or header_len
        return FetchResponse(
            url=requested_url,
            final_url=str(response.url),
            status_code=response.status_code,
            text=text,
            content_length=content_length,
            history=history,
            elapsed_ms=response.elapsed.total_seconds() * 1000,
            error=None,
        )

    def close(self) -> None:
        self.session.close()
