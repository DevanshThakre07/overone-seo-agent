from pathlib import Path

import responses

from app.config.settings import CrawlSettings
from app.crawler.crawler import WebsiteCrawler

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@responses.activate
def test_bfs_crawler_discovers_internal_pages():
    home = (FIXTURES / "sample_page.html").read_text(encoding="utf-8")
    about = "<html><head><title>About</title></head><body><h1>About</h1></body></html>"

    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/", body=home, status=200)
    responses.add(responses.GET, "https://example.com/sample", body=home, status=200)
    responses.add(responses.GET, "https://example.com/about", body=about, status=200)
    responses.add(responses.HEAD, "https://external.example/path", status=200)

    crawler = WebsiteCrawler(
        CrawlSettings(
            max_pages=10,
            max_depth=2,
            delay_seconds=0,
            respect_robots=True,
            check_external_links=False,
        )
    )
    results, stats = crawler.crawl("https://example.com/")
    crawler.close()

    urls = {r.final_url for r in results}
    assert stats.pages_crawled >= 1
    assert any("example.com" in u for u in urls)


@responses.activate
def test_broken_link_recorded():
    responses.add(responses.GET, "https://example.com/robots.txt", status=404)
    responses.add(responses.GET, "https://example.com/missing", status=404, body="gone")

    crawler = WebsiteCrawler(
        CrawlSettings(max_pages=1, delay_seconds=0, check_external_links=False)
    )
    results, stats = crawler.crawl("https://example.com/missing")
    crawler.close()
    assert results[0].status_code == 404
    assert stats.broken_count == 1
