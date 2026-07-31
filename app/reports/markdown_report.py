from __future__ import annotations

from app.models.audit import SiteAudit
from app.models.issues import Issue
from app.models.reports import ReportDocument
from app.reports.builder import build_report_document


def render_markdown(audit: SiteAudit) -> str:
    doc = build_report_document(audit)
    body = render_document_markdown(doc)
    metrics = (audit.summary or {}).get("seo_metrics") or {}
    if not metrics:
        return body
    return body.replace(
        "## Overall SEO Score",
        _render_seo_metrics_section(metrics) + "## Overall SEO Score",
        1,
    )


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
        "",
    ]
    return "\n".join(lines)


def render_document_markdown(doc: ReportDocument) -> str:
    s = doc.summary
    lines = [
        "# SEO Audit Report",
        "",
        f"**URL:** {s.seed_url}",
        f"**Audit ID:** {s.audit_id}",
        f"**Overall SEO Score:** {doc.overall_seo_score:.1f}/100",
        f"**Pages analyzed:** {s.pages_analyzed}",
    ]
    if s.created_at is not None:
        lines.append(f"**Created:** {s.created_at.isoformat()}")

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Overall SEO Score: **{doc.overall_seo_score:.1f}/100**",
            f"- Pages analyzed: {s.pages_analyzed}",
            f"- Critical issues: {s.critical_count}",
            f"- Warnings: {s.warning_count}",
            f"- Suggestions: {s.suggestion_count}",
        ]
    )
    if s.top_issue_codes:
        lines.append(f"- Top issue codes: {', '.join(s.top_issue_codes)}")
    for note in s.notes:
        lines.append(f"- Note: {note}")

    lines.extend(["", "## Critical Issues", ""])
    lines.extend(_issue_bullets(doc.critical_issues) or ["- None"])

    lines.extend(["", "## Warnings", ""])
    lines.extend(_issue_bullets(doc.warnings) or ["- None"])

    lines.extend(["", "## Suggestions", ""])
    lines.extend(_issue_bullets(doc.suggestions) or ["- None"])

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
                lines.append(f"- **Keywords:** {', '.join(page.keyword_suggestions)}")
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
                    ]
                )
            )
        lines.append("")

    # Prefer structured metrics from the audit summary when available via notes/overview.
    # ReportDocument itself carries page_overview; analyzer totals are reflected above.

    lines.extend(["## Overall SEO Score", "", f"**{doc.overall_seo_score:.1f} / 100**", ""])
    return "\n".join(lines)


def _issue_bullets(issues: list[Issue]) -> list[str]:
    return [
        f"- [{i.code}] {i.message}" + (f" (`{i.url}`)" if i.url else "") for i in issues
    ]
