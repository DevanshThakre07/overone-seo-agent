from __future__ import annotations

from app.crawler.client import FetchResponse, HttpClient
from app.crawler.sitemap import (
    coverage_vs_crawl,
    discover_sitemap_candidates,
    fetch_sitemap_snapshot,
)


class _FakeClient(HttpClient):
    def __init__(self, mapping: dict[str, FetchResponse]) -> None:
        # Bypass real session
        self.timeout = 5
        self.max_redirects = 3
        self.session = None  # type: ignore[assignment]
        self._mapping = mapping

    def get(self, url: str, *, stream: bool = False) -> FetchResponse:
        if url in self._mapping:
            return self._mapping[url]
        return FetchResponse(
            url=url,
            final_url=url,
            status_code=404,
            text="",
            content_length=0,
            history=[],
            elapsed_ms=1.0,
        )

    def close(self) -> None:
        return None


def test_discover_candidates_from_robots():
    client = _FakeClient(
        {
            "https://example.com/robots.txt": FetchResponse(
                url="https://example.com/robots.txt",
                final_url="https://example.com/robots.txt",
                status_code=200,
                text="User-agent: *\nSitemap: https://example.com/news-sitemap.xml\n",
                content_length=10,
                history=[],
                elapsed_ms=1.0,
            )
        }
    )
    cands = discover_sitemap_candidates("https://example.com/", client)
    assert cands[0] == "https://example.com/news-sitemap.xml"
    assert "https://example.com/sitemap.xml" in cands


def test_fetch_urlset_and_coverage():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/</loc></url>
      <url><loc>https://example.com/about</loc></url>
    </urlset>
    """
    client = _FakeClient(
        {
            "https://example.com/robots.txt": FetchResponse(
                url="https://example.com/robots.txt",
                final_url="https://example.com/robots.txt",
                status_code=404,
                text="",
                content_length=0,
                history=[],
                elapsed_ms=1.0,
            ),
            "https://example.com/sitemap.xml": FetchResponse(
                url="https://example.com/sitemap.xml",
                final_url="https://example.com/sitemap.xml",
                status_code=200,
                text=xml,
                content_length=len(xml),
                history=[],
                elapsed_ms=1.0,
            ),
        }
    )
    snap = fetch_sitemap_snapshot("https://example.com/", client)
    assert snap["status"] == "ok"
    assert snap["url_count"] == 2
    cov = coverage_vs_crawl(
        snap["urls"],
        ["https://example.com/", "https://example.com/pricing"],
        seed_url="https://example.com/",
    )
    assert cov["missing_count"] == 1
    assert any("pricing" in u for u in cov["missing_from_sitemap"])


def test_missing_sitemap_all_404():
    client = _FakeClient({})
    snap = fetch_sitemap_snapshot("https://example.com/", client)
    assert snap["status"] == "missing"
