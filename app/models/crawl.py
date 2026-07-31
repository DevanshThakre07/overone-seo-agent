from __future__ import annotations

from pydantic import BaseModel, Field


class RedirectHop(BaseModel):
    url: str
    status_code: int


class CrawlResult(BaseModel):
    url: str
    final_url: str
    status_code: int | None = None
    html: str | None = None
    content_length: int = 0
    redirect_chain: list[RedirectHop] = Field(default_factory=list)
    error: str | None = None
    depth: int = 0
    elapsed_ms: float = 0.0
    js_rendered: bool = False

    @property
    def is_broken(self) -> bool:
        if self.error:
            return True
        if self.status_code is None:
            return True
        return self.status_code >= 400


class CrawlStats(BaseModel):
    seed_url: str
    pages_crawled: int = 0
    pages_discovered: int = 0
    broken_count: int = 0
    redirect_count: int = 0
    errors: list[str] = Field(default_factory=list)
