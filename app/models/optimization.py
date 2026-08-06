from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FAQSuggestion(BaseModel):
    question: str
    answer: str


class InternalLinkSuggestion(BaseModel):
    anchor_text: str
    target_url: str
    rationale: str


class PageOptimization(BaseModel):
    url: str
    improved_title: str | None = None
    improved_meta_description: str | None = None
    improved_h1: str | None = None
    heading_suggestions: list[str] = Field(default_factory=list)
    keyword_suggestions: list[str] = Field(default_factory=list)
    faq_suggestions: list[FAQSuggestion] = Field(default_factory=list)
    schema_suggestion: dict[str, Any] | None = None
    internal_link_suggestions: list[InternalLinkSuggestion] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    url: str
    status: str = "ok"
    message: str = ""
    target_keywords: list[str] = Field(default_factory=list)
    keyword_research: dict[str, Any] = Field(default_factory=dict)
    page: PageOptimization | None = None
    pages: list[PageOptimization] = Field(default_factory=list)
    # Proof that suggestions came from the live page, not from guesswork.
    live_fetch: dict[str, Any] = Field(default_factory=dict)
    page_evidence: dict[str, Any] = Field(default_factory=dict)
    url_integrity: dict[str, Any] = Field(default_factory=dict)
    keyword_placement: dict[str, Any] = Field(default_factory=dict)
    analysis_is_site_specific: bool = True
    disclaimer: str | None = None
    # Explicit scope contract: these suggestions are for an external site and
    # must not be written into any local file (see app/utils/scope_guard.py).
    write_policy: dict[str, Any] = Field(default_factory=dict)
