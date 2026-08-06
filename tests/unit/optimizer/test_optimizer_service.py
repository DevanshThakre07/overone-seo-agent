import json

import responses

from app.config.settings import LLMSettings, Settings
from app.models.page import PageExtraction
from app.optimizer.llm_client import OpenAICompatibleClient
from app.services.optimizer_service import OptimizerService

SAMPLE_LLM_RESPONSE = {
    "improved_title": "Sample SEO Page | Example",
    "improved_meta_description": "Learn about sample SEO features with clear, helpful content.",
    "improved_h1": "Sample SEO Page",
    "heading_suggestions": ["Why this matters", "Key features"],
    "keyword_suggestions": ["sample seo", "seo page"],
    "faq_suggestions": [
        {"question": "What is this page?", "answer": "A sample SEO page for testing."}
    ],
    "schema_suggestion": {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Sample SEO Page",
    },
    "internal_link_suggestions": [
        {
            "anchor_text": "About us",
            "target_url": "https://example.com/about",
            "rationale": "Supports topical relevance",
        }
    ],
    "notes": ["Grounded in extracted fields only"],
}


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def complete(self, messages, *, temperature=None):  # noqa: ANN001
        self.calls += 1
        return self.content


def test_optimize_page_with_injected_page(monkeypatch):
    monkeypatch.setenv("KEYWORD_API_PROVIDER", "")
    monkeypatch.setenv("KEYWORD_API_LOGIN", "")
    monkeypatch.setenv("KEYWORD_API_PASSWORD", "")
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()

    page = PageExtraction(
        url="https://example.com/sample",
        final_url="https://example.com/sample",
        title="Sample SEO Page",
        meta_description="A sample page used for SEO extractor tests.",
        h1=["Welcome to Sample SEO Page"],
        h2=["Features"],
        internal_links=["https://example.com/about"],
    )
    service = OptimizerService(
        settings=Settings(llm=LLMSettings(model="test-model")),
        llm_client=FakeLLM(json.dumps(SAMPLE_LLM_RESPONSE)),
    )
    # bypass missing API key path by injecting fake client
    result = service.optimize_page(
        "https://example.com/sample",
        page=page,
        target_keywords=["seo"],
    )
    assert result.status == "ok"
    assert result.page is not None
    assert result.page.improved_title == "Sample SEO Page | Example"
    assert result.page.faq_suggestions[0].question.startswith("What is")
    assert result.page.internal_link_suggestions[0].target_url.endswith("/about")
    assert result.keyword_research["status"] == "caller_provided_not_researched"
    assert result.keyword_research["is_real_research"] is False
    assert result.target_keywords == ["seo"]
    settings_module.get_settings.cache_clear()


def test_optimize_page_without_keywords_does_not_fake_research(monkeypatch):
    monkeypatch.setenv("KEYWORD_API_PROVIDER", "")
    monkeypatch.setenv("KEYWORD_API_LOGIN", "")
    monkeypatch.setenv("KEYWORD_API_PASSWORD", "")
    from app.config import settings as settings_module

    settings_module.get_settings.cache_clear()

    page = PageExtraction(
        url="https://example.com/sample",
        final_url="https://example.com/sample",
        title="Actoro App",
        h1=["Actoro"],
    )
    service = OptimizerService(
        settings=Settings(llm=LLMSettings(model="test-model")),
        llm_client=FakeLLM(json.dumps(SAMPLE_LLM_RESPONSE)),
    )
    result = service.optimize_page("https://example.com/sample", page=page)
    assert result.status == "ok"
    assert result.keyword_research["status"] == "not_provided"
    assert result.keyword_research["is_real_research"] is False
    assert result.page is not None
    assert result.page.keyword_suggestions == []
    assert any("keyword" in n.lower() or "api" in n.lower() for n in result.page.notes)
    settings_module.get_settings.cache_clear()


@responses.activate
def test_openai_compatible_client_posts_chat_completions():
    responses.add(
        responses.POST,
        "https://api.openai.com/v1/chat/completions",
        json={
            "choices": [
                {"message": {"content": '{"improved_title":"X","notes":[]}'}}
            ]
        },
        status=200,
    )
    client = OpenAICompatibleClient(
        LLMSettings(base_url="https://api.openai.com/v1", model="gpt-4o-mini"),
        api_key="test-key",
    )
    content = client.complete([{"role": "user", "content": "hi"}])
    assert "improved_title" in content
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-key"


def test_optimize_without_api_key_returns_error():
    service = OptimizerService(
        settings=Settings(openai_api_key=None, llm=LLMSettings()),
        llm_client=OpenAICompatibleClient(LLMSettings(), api_key=None),
    )
    page = PageExtraction(
        url="https://example.com",
        final_url="https://example.com",
        title="T",
        h1=["H"],
    )
    result = service.optimize_page("https://example.com", page=page)
    assert result.status == "error"
    assert "OPENAI_API_KEY" in result.message
