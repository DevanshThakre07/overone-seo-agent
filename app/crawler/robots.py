"""robots.txt helper."""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from app.crawler.client import HttpClient


class RobotsChecker:
    def __init__(self, client: HttpClient, user_agent: str) -> None:
        self.client = client
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        parser = self._parsers.get(host)
        if parser is None:
            parser = self._load(url)
            self._parsers[host] = parser
        return parser.can_fetch(self.user_agent, url)

    def _load(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        fetch = self.client.get(robots_url)
        if fetch.error or fetch.status_code >= 400:
            # Fail open if robots.txt missing/unreachable
            rp.parse([])
            return rp
        rp.parse(fetch.text.splitlines())
        return rp
