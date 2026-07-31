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
    page: PageOptimization | None = None
    pages: list[PageOptimization] = Field(default_factory=list)
