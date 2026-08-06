from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ImageInfo(BaseModel):
    src: str
    alt: str | None = None
    # alt="" is VALID HTML for decorative images and must not be reported as a
    # missing attribute. These fields keep the two cases distinguishable.
    alt_present: bool = False
    decorative: bool = False
    # <source> inside <picture> carries no alt attribute by spec — the alt lives
    # on the sibling <img>, so these must be excluded from alt checks.
    is_source: bool = False


class PageExtraction(BaseModel):
    url: str
    final_url: str
    status_code: int | None = None
    title: str | None = None
    meta_description: str | None = None
    h1: list[str] = Field(default_factory=list)
    h2: list[str] = Field(default_factory=list)
    h3: list[str] = Field(default_factory=list)
    h4: list[str] = Field(default_factory=list)
    h5: list[str] = Field(default_factory=list)
    h6: list[str] = Field(default_factory=list)
    images: list[ImageInfo] = Field(default_factory=list)
    canonical: str | None = None
    robots_meta: str | None = None
    internal_links: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)
    content_length: int = 0
    redirect_chain: list[str] = Field(default_factory=list)
    is_broken: bool = False
    error: str | None = None
    has_json_ld: bool = False
    schema_types: list[str] = Field(default_factory=list)
    # Enriched extraction fields (backward-compatible additions)
    title_source: str | None = None
    meta_description_source: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    twitter_title: str | None = None
    twitter_description: str | None = None
    lang: str | None = None
    has_viewport: bool = False
    word_count: int = 0
    text_length: int = 0
    internal_link_occurrences: int = 0
    external_link_occurrences: int = 0
    image_count: int = 0
    js_rendered: bool = False
    # Bounded visible-text sample so downstream analysis (keyword presence,
    # prompts) can work from real page copy without storing full documents.
    text_sample: str = ""
    extraction_warnings: list[str] = Field(default_factory=list)
    seo_signals: dict[str, Any] = Field(default_factory=dict)
