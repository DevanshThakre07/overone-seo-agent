"""BFS website crawler."""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from app.config.settings import CrawlSettings, PlaywrightSettings
from app.crawler.client import HttpClient
from app.crawler.playwright_client import PlaywrightClient
from app.crawler.robots import RobotsChecker
from app.logging import get_logger, log_event
from app.models.crawl import CrawlResult, CrawlStats, RedirectHop
from app.utils.url import is_same_host, normalize_url, resolve_url

logger = get_logger(__name__)

THIN_CONTENT_THRESHOLD = 200


class WebsiteCrawler:
    def __init__(
        self,
        crawl_settings: CrawlSettings,
        playwright_settings: PlaywrightSettings | None = None,
        client: HttpClient | None = None,
    ) -> None:
        self.settings = crawl_settings
        self.client = client or HttpClient(
            user_agent=crawl_settings.user_agent,
            timeout=crawl_settings.timeout_seconds,
            max_redirects=crawl_settings.max_redirects,
        )
        self.robots = RobotsChecker(self.client, crawl_settings.user_agent)
        self.playwright = PlaywrightClient(playwright_settings or PlaywrightSettings())

    def crawl(self, seed_url: str) -> tuple[list[CrawlResult], CrawlStats]:
        seed = normalize_url(seed_url)
        log_event(logger, "crawl_started", url=seed)

        stats = CrawlStats(seed_url=seed)
        results: list[CrawlResult] = []
        seen: set[str] = {seed}
        queue: deque[tuple[str, int]] = deque([(seed, 0)])
        discovered_links: set[str] = set()

        while queue and len(results) < self.settings.max_pages:
            url, depth = queue.popleft()

            if self.settings.respect_robots and not self.robots.allowed(url):
                results.append(
                    CrawlResult(
                        url=url,
                        final_url=url,
                        status_code=403,
                        error="Blocked by robots.txt",
                        depth=depth,
                    )
                )
                stats.broken_count += 1
                continue

            if self.settings.delay_seconds > 0 and results:
                time.sleep(self.settings.delay_seconds)

            result = self._fetch_page(url, depth)
            results.append(result)

            if result.is_broken:
                stats.broken_count += 1
            if result.redirect_chain:
                stats.redirect_count += 1
            if result.error:
                stats.errors.append(f"{url}: {result.error}")

            if result.html and depth < self.settings.max_depth:
                for link in self._extract_links(result.html, result.final_url):
                    discovered_links.add(link)
                    if link in seen:
                        continue
                    if self.settings.same_host_only and not is_same_host(seed, link):
                        continue
                    seen.add(link)
                    queue.append((link, depth + 1))

        stats.pages_crawled = len(results)
        stats.pages_discovered = len(seen | discovered_links)
        log_event(
            logger,
            "pages_discovered",
            url=seed,
            pages_crawled=stats.pages_crawled,
            pages_discovered=stats.pages_discovered,
        )

        if self.settings.check_external_links:
            self._check_external_links(results, seed)

        return results, stats

    def _fetch_page(self, url: str, depth: int) -> CrawlResult:
        fetch = self.client.get(url)
        redirect_chain = [
            RedirectHop(url=h_url, status_code=code) for h_url, code in fetch.history
        ]
        if fetch.history:
            redirect_chain.append(
                RedirectHop(url=fetch.final_url, status_code=fetch.status_code)
            )

        html = fetch.text
        js_rendered = False
        # Upgrade via Playwright when the static HTML is thin OR looks like a
        # client-rendered shell (common SPA root with almost no SEO tags).
        if (
            not fetch.error
            and fetch.status_code
            and fetch.status_code < 400
            and (self._looks_thin(html) or self._looks_like_spa_shell(html))
        ):
            pw_html = self.playwright.fetch(url)
            if pw_html:
                html = pw_html
                js_rendered = True

        body_len = len((html or "").encode("utf-8", errors="ignore"))
        # Prefer measured body size; Content-Length headers are often missing/wrong.
        content_length = body_len or fetch.content_length

        return CrawlResult(
            url=url,
            final_url=normalize_url(fetch.final_url) if fetch.final_url else url,
            status_code=fetch.status_code or None,
            html=html if not fetch.error else None,
            content_length=content_length,
            redirect_chain=redirect_chain,
            error=fetch.error,
            depth=depth,
            elapsed_ms=fetch.elapsed_ms,
            js_rendered=js_rendered,
        )

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        soup = self._soup(html)
        links: list[str] = []
        for tag in soup.find_all("a", href=True):
            href = str(tag.get("href") or "").strip()
            if not href or href.startswith("#"):
                continue
            lowered = href.lower()
            if lowered.startswith(("javascript:", "mailto:", "tel:", "sms:", "data:")):
                continue
            resolved = resolve_url(base_url, href)
            if resolved:
                links.append(resolved)
        return links

    def _looks_thin(self, html: str) -> bool:
        if not html:
            return True
        soup = self._soup(html)
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return len(text) < THIN_CONTENT_THRESHOLD

    def _looks_like_spa_shell(self, html: str) -> bool:
        """Detect common JS app shells where SEO tags are injected client-side."""
        if not html:
            return True
        soup = self._soup(html)
        h1_count = len([h for h in soup.find_all("h1") if h.get_text(strip=True)])
        img_count = len(soup.find_all("img"))
        a_count = len(soup.find_all("a", href=True))
        rootish = soup.find(
            id=lambda v: isinstance(v, str)
            and v.lower() in {"root", "app", "__next", "___gatsby"}
        )
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text_len = len(soup.get_text(" ", strip=True))
        semantic = h1_count + img_count + a_count
        if rootish is not None and semantic == 0:
            return True
        if semantic == 0 and text_len < 120:
            return True
        return False

    @staticmethod
    def _soup(html: str) -> BeautifulSoup:
        try:
            return BeautifulSoup(html, "lxml")
        except Exception:
            return BeautifulSoup(html, "html.parser")

    def _check_external_links(self, results: list[CrawlResult], seed: str) -> None:
        """Probe external links found on crawled pages (capped)."""
        externals: list[str] = []
        for result in results:
            if not result.html:
                continue
            for link in self._extract_links(result.html, result.final_url):
                if not is_same_host(seed, link) and link not in externals:
                    externals.append(link)
                if len(externals) >= self.settings.max_external_link_checks:
                    break

        if not externals:
            return

        broken: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=self.settings.concurrency) as pool:
            futures = {pool.submit(self.client.head, url): url for url in externals}
            for future in as_completed(futures):
                url = futures[future]
                fetch = future.result()
                if fetch.error or (fetch.status_code and fetch.status_code >= 400):
                    broken[url] = fetch.error or f"HTTP {fetch.status_code}"

        # Attach broken external markers onto crawl results via error notes on seed stats later;
        # store as synthetic CrawlResult entries for the analyzer.
        for url, err in broken.items():
            results.append(
                CrawlResult(
                    url=url,
                    final_url=url,
                    status_code=0,
                    error=err,
                    depth=-1,
                )
            )

    def close(self) -> None:
        self.client.close()
