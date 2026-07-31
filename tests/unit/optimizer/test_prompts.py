import json

from app.models.page import PageExtraction
from app.optimizer.prompts import build_page_optimization_messages, parse_optimization_json


def test_build_messages_includes_page_facts():
    page = PageExtraction(
        url="https://example.com",
        final_url="https://example.com",
        title="Old Title",
        meta_description=None,
        h1=["Hello"],
        internal_links=["https://example.com/about"],
    )
    messages = build_page_optimization_messages(page, target_keywords=["seo"])
    assert messages[0]["role"] == "system"
    assert "Old Title" in messages[1]["content"]
    assert "seo" in messages[1]["content"]


def test_parse_optimization_json_strips_fences():
    raw = """```json
{"improved_title": "Better Title", "notes": []}
```"""
    data = parse_optimization_json(raw)
    assert data["improved_title"] == "Better Title"
    assert json.dumps(data)  # serializable
