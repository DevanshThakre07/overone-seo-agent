from __future__ import annotations

from app.models.audit import SiteAudit
from app.models.issues import Issue
from app.models.reports import ReportDocument
from app.reports.builder import build_report_document


def render_markdown(audit: SiteAudit) -> str:
    doc = build_report_document(audit)
    body = render_document_markdown(doc)
    summary = audit.summary or {}

    sections = ""
    metrics = summary.get("seo_metrics") or {}
    if metrics:
        sections += _render_seo_metrics_section(metrics)
    sections += _render_data_integrity_section(summary)
    sections += _render_keyword_research_section(summary)

    if sections:
        body = body.replace("## Overall SEO Score", sections + "## Overall SEO Score", 1)
    return _strip_diff_markers(body)


def _strip_diff_markers(text: str) -> str:
    """Guarantee clean markdown even if diff-formatted text reaches the renderer."""
    lines = text.splitlines()
    body = [ln for ln in lines if ln.strip()]
    if body and all(ln.startswith(("+", "-")) for ln in body):
        return "\n".join(ln[1:] if ln[:1] in {"+", "-"} else ln for ln in lines)
    return text


def _render_data_integrity_section(summary: dict) -> str:
    integrity = summary.get("url_integrity") or {}
    if not integrity:
        return ""
    lines = ["## Data Integrity", ""]
    if integrity.get("ok") and integrity.get("exact_match"):
        lines.append(
            f"- Verified: results are for the requested URL "
            f"({integrity.get('requested_url')})."
        )
    elif integrity.get("warning"):
        lines.append(f"- **{integrity['warning']}**")
    lines.append("")
    return "\n".join(lines) + "\n"


def _render_keyword_research_section(summary: dict) -> str:
    """Report research status; show metrics when DataForSEO (or similar) ran."""
    kr = summary.get("keyword_research") or {}
    research = kr.get("research") or {}
    metrics = kr.get("metrics") or research.get("keywords") or []
    lines = [
        "## Keyword Research",
        "",
        f"- Status: **{kr.get('status', 'unavailable')}**",
        f"- Real research: **{'yes' if kr.get('is_real_research') else 'no'}**",
    ]
    if kr.get("provider") or research.get("provider"):
        lines.append(
            f"- Provider: `{kr.get('provider') or research.get('provider')}`"
        )
    if kr.get("message"):
        lines.append(f"- {kr['message']}")

    if metrics and kr.get("is_real_research"):
        lines.extend(
            [
                "",
                "| Keyword | Volume | CPC | Competition | Difficulty |",
                "| --- | ---: | ---: | --- | ---: |",
            ]
        )
        for row in metrics[:40]:
            lines.append(
                "| {kw} | {vol} | {cpc} | {comp} | {diff} |".format(
                    kw=row.get("keyword") or "",
                    vol=row.get("search_volume")
                    if row.get("search_volume") is not None
                    else "—",
                    cpc=row.get("cpc") if row.get("cpc") is not None else "—",
                    comp=row.get("competition") or "—",
                    diff=row.get("keyword_difficulty")
                    if row.get("keyword_difficulty") is not None
                    else "—",
                )
            )
        related = kr.get("related") or research.get("related") or []
        if related:
            lines.extend(["", "### Related keywords", ""])
            for row in related[:20]:
                lines.append(
                    f"- **{row.get('keyword')}** — volume "
                    f"{row.get('search_volume') if row.get('search_volume') is not None else '—'}, "
                    f"difficulty "
                    f"{row.get('keyword_difficulty') if row.get('keyword_difficulty') is not None else '—'}"
                )
        lines.append("")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "",
            "Keyword **placement** on the live page is separate from research. "
            "Without a keyword API, SEO-Agent will not invent volume or difficulty.",
            "",
            "Configure DataForSEO in `.env`:",
            "",
            "```bash",
            "KEYWORD_API_PROVIDER=dataforseo",
            "KEYWORD_API_LOGIN=...",
            "KEYWORD_API_PASSWORD=...",
            "```",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_seo_metrics_section(metrics: dict) -> str:
    coverage = metrics.get("coverage") or {}
    totals = metrics.get("totals") or {}
    rendering = metrics.get("rendering") or {}
    lines = [
        "## Structured SEO Metrics",
        "",
        f"- Live pages: {metrics.get('pages_live', 0)} / {metrics.get('pages_total', 0)}",
        f"- Broken pages: {metrics.get('pages_broken', 0)}",
        f"- Titles present: {coverage.get('titles', 0)}",
        f"- Meta descriptions present: {coverage.get('meta_descriptions', 0)}",
        f"- Pages with H1: {coverage.get('h1', 0)}",
        f"- Pages with canonical: {coverage.get('canonical', 0)}",
        f"- Pages with schema: {coverage.get('schema', 0)}",
        f"- Total H1/H2/H3: {totals.get('h1', 0)}/{totals.get('h2', 0)}/{totals.get('h3', 0)}",
        f"- Images: {totals.get('images', 0)}",
        f"- Internal links (unique / occurrences): "
        f"{totals.get('internal_links_unique', 0)} / {totals.get('internal_link_occurrences', 0)}",
        f"- Word count (all pages): {totals.get('word_count', 0)}",
        f"- JS shell pages / JS-rendered pages: "
        f"{rendering.get('js_shell_pages', 0)} / {rendering.get('js_rendered_pages', 0)}",
        f"- Rendering incomplete: {rendering.get('rendering_incomplete', False)}",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_document_markdown(doc: ReportDocument) -> str:
    s = doc.summary
    lines = [
        "# SEO Audit Report",
        "",
        f"**URL:** {s.seed_url}",
        f"**Audit ID:** {s.audit_id}",
        f"**Pages analyzed:** {s.pages_analyzed}",
    ]
    if s.rendering_warning or (getattr(s, "score_note", None)):
        lines.append(
            f"**Overall SEO Score:** PROVISIONAL / WITHHELD "
            f"(raw issue figure {doc.overall_seo_score:.1f}/100 is not a reliable grade)"
        )
    else:
        lines.append(f"**Overall SEO Score:** {doc.overall_seo_score:.1f}/100")
    if s.created_at is not None:
        lines.append(f"**Created:** {s.created_at.isoformat()}")

    lines.extend(["", "## Audit Scope", ""])
    if s.scope_note:
        lines.append(f"> {s.scope_note}")
    else:
        lines.append(
            f"> This audit analyzed {s.pages_analyzed} page(s) starting from {s.seed_url}."
        )
    if doc.scope:
        lines.append("")
        lines.append(
            f"- max_pages limit: {doc.scope.get('max_pages_limit', 'n/a')}"
        )
        lines.append(
            f"- max_depth limit: {doc.scope.get('max_depth_limit', 'n/a')}"
        )

    if s.rendering_warning:
        lines.extend(
            [
                "",
                "## Rendering Warning",
                "",
                f"> **CRITICAL:** {s.rendering_warning}",
                "",
                "Content-based findings (H1, links, images, schema) from unrendered "
                "JS shells were suppressed. Score is provisional until Playwright "
                "captures the rendered DOM. Check `rendering.page_diagnostics` in JSON.",
            ]
        )

    lines.extend(
        [
            "",
            "## Summary",
            "",
        ]
    )
    if s.rendering_warning:
        lines.append(
            f"- Overall SEO Score: **PROVISIONAL / WITHHELD** "
            f"(raw {doc.overall_seo_score:.1f}/100 — incomplete data)"
        )
    else:
        lines.append(f"- Overall SEO Score: **{doc.overall_seo_score:.1f}/100**")
    lines.extend(
        [
            f"- Pages analyzed: {s.pages_analyzed}",
            f"- Critical issues: {s.critical_count}",
            f"- Warnings: {s.warning_count}",
            f"- Suggestions: {s.suggestion_count}",
        ]
    )
    if s.top_issue_codes:
        lines.append(f"- Top issue codes: {', '.join(s.top_issue_codes)}")
    for note in s.notes:
        if note and note != s.scope_note and note != s.rendering_warning:
            lines.append(f"- Note: {note}")

    lines.extend(["", "## Critical Issues", ""])
    lines.extend(_issue_bullets(doc.critical_issues) or ["- None"])

    lines.extend(["", "## Warnings", ""])
    lines.extend(_issue_bullets(doc.warnings) or ["- None"])

    lines.extend(["", "## Suggestions", ""])
    lines.extend(_issue_bullets(doc.suggestions) or ["- None"])

    lines.extend(["", "## Recommendations", ""])
    if not doc.recommendations:
        lines.append("- None")
    else:
        for rec in doc.recommendations:
            lines.append(f"### {rec.get('url')}")
            lines.append("")
            if rec.get("rendering_unreliable"):
                lines.append(
                    "- Rendering unreliable — fix Playwright capture before applying copy changes."
                )
                lines.append("")
                continue
            rewrites = rec.get("rewrites") or {}
            title_rw = rewrites.get("title") or {}
            meta_rw = rewrites.get("meta_description") or {}
            h1_rw = rewrites.get("h1") or {}
            # Only show a rewrite when it actually changes the copy.
            if title_rw and title_rw.get("current") != title_rw.get("suggested"):
                lines.append(
                    f'- **Title rewrite:** `{title_rw.get("current")}` → '
                    f'**"{title_rw.get("suggested")}"** '
                    f'({title_rw.get("suggested_length")} chars)'
                )
            if meta_rw and meta_rw.get("current") != meta_rw.get("suggested"):
                lines.append(
                    f'- **Meta rewrite:** `{meta_rw.get("current")}` → '
                    f'**"{meta_rw.get("suggested")}"** '
                    f'({meta_rw.get("suggested_length")} chars)'
                )
            if h1_rw and h1_rw.get("current") != h1_rw.get("suggested"):
                lines.append(
                    f'- **H1 rewrite:** `{h1_rw.get("current")}` → '
                    f'**"{h1_rw.get("suggested")}"**'
                )
            for action in rec.get("actions") or []:
                if action.get("code") in {
                    "title_rewrite",
                    "meta_rewrite",
                    "missing_title",
                    "missing_meta_description",
                    "missing_h1",
                }:
                    continue  # already shown as concrete rewrites above
                lines.append(f"- {action.get('message')}")
            lines.append("")

    if doc.diff is not None:
        lines.extend(
            [
                "",
                "## Change Report",
                "",
                f"- Has baseline: {doc.diff.has_baseline}",
                f"- Score delta: {doc.diff.score_delta:+.1f}",
                f"- New issues: {len(doc.diff.new_issues)}",
                f"- Resolved issues: {len(doc.diff.resolved_issues)}",
                f"- {doc.diff.summary}",
                "",
            ]
        )

    if doc.optimization and doc.optimization.pages:
        lines.extend(["", "## AI Optimization Suggestions", ""])
        kr = doc.optimization.keyword_research or {}
        if kr:
            lines.append(
                f"- Keyword research status: **{kr.get('status', 'unavailable')}**"
            )
            if kr.get("message"):
                lines.append(f"- {kr['message']}")
            research = kr.get("research") or {}
            if research.get("message"):
                lines.append(f"- {research['message']}")
            lines.append("")
        for page in doc.optimization.pages:
            lines.append(f"### {page.url}")
            lines.append("")
            if page.improved_title:
                lines.append(f"- **Title:** {page.improved_title}")
            if page.improved_meta_description:
                lines.append(f"- **Meta description:** {page.improved_meta_description}")
            if page.improved_h1:
                lines.append(f"- **H1:** {page.improved_h1}")
            if page.keyword_suggestions:
                lines.append(f"- **Keywords (caller-provided only):** {', '.join(page.keyword_suggestions)}")
            elif kr.get("status") != "caller_provided":
                lines.append(
                    "- **Keywords:** none — keyword research API not configured "
                    "(brand/title guesses are not treated as research)."
                )
            if page.heading_suggestions:
                lines.append("- **Headings:**")
                lines.extend([f"  - {h}" for h in page.heading_suggestions])
            if page.faq_suggestions:
                lines.append("- **FAQs:**")
                for faq in page.faq_suggestions:
                    lines.append(f"  - Q: {faq.question}")
                    lines.append(f"    A: {faq.answer}")
            if page.internal_link_suggestions:
                lines.append("- **Internal links:**")
                for link in page.internal_link_suggestions:
                    lines.append(
                        f"  - [{link.anchor_text}]({link.target_url}) — {link.rationale}"
                    )
            if page.schema_suggestion:
                lines.append("- **Schema:** JSON-LD suggestion included in JSON report")
            if page.notes:
                lines.append("- **Notes:**")
                lines.extend([f"  - {n}" for n in page.notes])
            lines.append("")

    if doc.page_overview:
        lines.extend(["## Page Overview", ""])
        for page in doc.page_overview:
            status = "broken" if page.get("is_broken") else page.get("status_code")
            title = page.get("title") or "(no title)"
            lines.append(f"- `{page.get('url')}` — {title} [{status}]")
            lines.append(
                "  - "
                + ", ".join(
                    [
                        f"title_len={page.get('title_length', 0)}",
                        f"meta_len={page.get('meta_description_length', 0)}",
                        f"h1={page.get('h1_count', 0)}",
                        f"h2={page.get('h2_count', 0)}",
                        f"h3={page.get('h3_count', 0)}",
                        f"images={page.get('image_count', 0)}",
                        f"missing_alt={page.get('images_missing_alt', 0)}",
                        f"internal_links={page.get('internal_links', 0)}",
                        f"words={page.get('word_count', 0)}",
                        f"schema={','.join(page.get('schema_types') or []) or 'none'}",
                        f"js_rendered={page.get('js_rendered', False)}",
                    ]
                )
            )
        lines.append("")

    lines.extend(["## Overall SEO Score", ""])
    if s.rendering_warning or getattr(s, "score_note", None):
        lines.extend(
            [
                "**PROVISIONAL — score withheld.**",
                "",
                f"The raw issue-based figure is {doc.overall_seo_score:.1f}/100, but it is "
                "not a reliable grade: content findings were suppressed because the page "
                "was not fully rendered. Fix JS rendering, then re-run for a real score.",
                "",
            ]
        )
    else:
        lines.extend([f"**{doc.overall_seo_score:.1f} / 100**", ""])

    mode_note = getattr(s, "scoring_mode_note", None)
    if mode_note:
        lines.extend([f"_Scoring basis: {mode_note}_", ""])
    return "\n".join(lines)


def _issue_bullets(issues: list[Issue]) -> list[str]:
    return [
        f"- [{i.code}] {i.message}" + (f" (`{i.url}`)" if i.url else "") for i in issues
    ]
