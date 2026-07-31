"""Hermes plugin: SEO-Agent tools.

Installed by symlink into ~/.hermes/plugins/seo-agent — does not modify
the hermes-agent repository.
"""

from __future__ import annotations

from . import handlers, schemas

_TOOLS = (
    ("audit_site", schemas.AUDIT_SITE, handlers.handle_audit_site, "🔍"),
    ("optimize_page", schemas.OPTIMIZE_PAGE, handlers.handle_optimize_page, "✨"),
    ("generate_report", schemas.GENERATE_REPORT, handlers.handle_generate_report, "📄"),
    ("compare_audits", schemas.COMPARE_AUDITS, handlers.handle_compare_audits, "📊"),
    ("list_seo_history", schemas.LIST_SEO_HISTORY, handlers.handle_list_seo_history, "🗂️"),
)


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
