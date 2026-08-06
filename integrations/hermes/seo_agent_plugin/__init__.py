"""Hermes plugin: SEO-Agent tools.

Installed by symlink into ~/.hermes/plugins/seo-agent — does not modify
the hermes-agent repository.
"""

from __future__ import annotations

from . import handlers, schemas

_TOOLS = (
    ("audit_site", schemas.AUDIT_SITE, handlers.handle_audit_site, "🔍"),
    ("check_pagespeed", schemas.CHECK_PAGESPEED, handlers.handle_check_pagespeed, "⚡"),
    (
        "research_keywords",
        schemas.RESEARCH_KEYWORDS,
        handlers.handle_research_keywords,
        "📈",
    ),
    ("optimize_page", schemas.OPTIMIZE_PAGE, handlers.handle_optimize_page, "✨"),
    ("keyword_plan", schemas.KEYWORD_PLAN, handlers.handle_keyword_plan, "🔑"),
    ("generate_report", schemas.GENERATE_REPORT, handlers.handle_generate_report, "📄"),
    ("compare_audits", schemas.COMPARE_AUDITS, handlers.handle_compare_audits, "📊"),
    (
        "confirm_site_sources",
        schemas.CONFIRM_SITE_SOURCES,
        handlers.handle_confirm_site_sources,
        "🔒",
    ),
    ("list_seo_history", schemas.LIST_SEO_HISTORY, handlers.handle_list_seo_history, "🗂️"),
)


def _load_pre_tool_call_hook():
    """Import the write firewall from the SEO-Agent tree (added to sys.path)."""
    handlers._ensure_seo_path()
    from app.utils.write_firewall import pre_tool_call_hook

    return pre_tool_call_hook


def register(ctx) -> None:
    """Called by Hermes plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="seo-agent",
            schema=schema,
            handler=handler,
            check_fn=handlers._check_seo_available,
            emoji=emoji,
            description=schema.get("description", ""),
        )

    # Real enforcement. Prose in the tool output was routed around twice; a
    # pre_tool_call block is the only thing the model cannot talk its way past.
    ctx.register_hook("pre_tool_call", _load_pre_tool_call_hook())
