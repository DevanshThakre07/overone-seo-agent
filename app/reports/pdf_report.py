"""PDF report renderer (fpdf2 optional extra: seo-agent[pdf])."""

from __future__ import annotations

import io
from typing import Any

from app.models.audit import SiteAudit
from app.models.reports import ReportDocument
from app.reports.builder import build_report_document

PDF_EXTRA_HINT = (
    "PDF reports require the optional dependency. "
    "Install with: pip install 'seo-agent[pdf]' (or pip install fpdf2)."
)


class PdfNotImplementedError(NotImplementedError):
    """Raised when PDF support is unavailable or not implemented."""


class PdfDependencyError(PdfNotImplementedError):
    """Raised when fpdf2 is not installed."""


def _require_fpdf():
    try:
        from fpdf import FPDF  # noqa: F401
    except ImportError as exc:
        raise PdfDependencyError(PDF_EXTRA_HINT) from exc
    from fpdf import FPDF

    return FPDF


def render_pdf(audit: SiteAudit) -> bytes:
    document = build_report_document(audit)
    return render_document_pdf(document, audit=audit)


def render_document_pdf(
    document: ReportDocument, *, audit: SiteAudit | None = None
) -> bytes:
    FPDF = _require_fpdf()

    class _ReportPDF(FPDF):
        def __init__(self, audit_id: str) -> None:
            super().__init__()
            self._audit_id = audit_id

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("Helvetica", size=8)
            self.set_text_color(100, 100, 100)
            self.cell(
                0,
                8,
                f"SEO Agent | {self._audit_id} | page {self.page_no()}/{{nb}}",
                align="C",
            )

    summary = document.summary
    pdf = _ReportPDF(summary.audit_id)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    # Header / brand
    pdf.set_fill_color(28, 26, 23)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(246, 243, 238)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(12, 8)
    pdf.cell(186, 8, "SEO Agent", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_x(12)
    pdf.cell(186, 5, "Technical SEO audit report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(34)

    pdf.set_text_color(28, 26, 23)
    _safe_multi(pdf, summary.seed_url, size=12, style="B")
    pdf.set_font("Helvetica", size=9)
    created = summary.created_at.isoformat() if summary.created_at else "-"
    pdf.set_x(12)
    pdf.cell(186, 6, f"Audit date: {created}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(12)
    pdf.cell(
        186,
        6,
        f"Pages analyzed: {summary.pages_analyzed}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # Score block
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(13, 92, 69)
    pdf.set_x(12)
    pdf.cell(
        186,
        12,
        f"{summary.overall_seo_score:.0f} / 100",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(28, 26, 23)
    pdf.set_font("Helvetica", size=10)
    pdf.set_x(12)
    pdf.cell(
        186,
        6,
        (
            f"Critical: {summary.critical_count}  |  "
            f"Warning: {summary.warning_count}  |  "
            f"Info: {summary.suggestion_count}"
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    if summary.scope_note:
        _section(pdf, "Scope")
        _safe_multi(pdf, summary.scope_note, size=9)

    if summary.notes:
        _section(pdf, "Notes")
        for note in summary.notes[:8]:
            _bullet(pdf, note)

    _issue_section(pdf, "Critical issues", document.critical_issues, limit=15)
    _issue_section(pdf, "Warnings", document.warnings, limit=20)
    _issue_section(pdf, "Suggestions", document.suggestions, limit=20)

    if document.recommendations:
        _section(pdf, "Recommendations")
        for rec in document.recommendations[:8]:
            url = rec.get("url") or ""
            if url:
                _safe_multi(pdf, str(url), size=9, style="B")
            for action in (rec.get("actions") or [])[:5]:
                msg = action.get("message") or action.get("code") or ""
                if msg:
                    _bullet(pdf, str(msg))
            pdf.ln(1)

    _optimization_section(pdf, document.optimization)

    if audit is not None:
        _summary_integrations(pdf, audit.summary or {})

    if document.page_overview:
        _section(pdf, "Page overview")
        for row in document.page_overview[:12]:
            title = row.get("title") or "(no title)"
            line = f"{row.get('status_code', '—')} · {row.get('url', '')} · {title}"
            _bullet(pdf, line)

    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()


def _section(pdf: Any, title: str) -> None:
    pdf.ln(3)
    pdf.set_x(12)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(13, 92, 69)
    pdf.cell(186, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(28, 26, 23)
    pdf.set_draw_color(207, 198, 184)
    y = pdf.get_y()
    pdf.line(12, y, 198, y)
    pdf.ln(3)


def _bullet(pdf: Any, text: str) -> None:
    pdf.set_x(12)
    pdf.set_font("Helvetica", size=9)
    cleaned = _latin1_safe(text)
    pdf.multi_cell(186, 5, f"- {cleaned}")


def _safe_multi(pdf: Any, text: str, *, size: int = 9, style: str = "") -> None:
    pdf.set_x(12)
    pdf.set_font("Helvetica", style, size)
    pdf.multi_cell(186, 5, _latin1_safe(text))


def _latin1_safe(text: str) -> str:
    """Helvetica core fonts are Latin-1; replace unsupported glyphs."""
    return (
        (text or "")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2026", "...")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def _issue_section(pdf: Any, title: str, issues: list, *, limit: int) -> None:
    if not issues:
        return
    _section(pdf, title)
    for issue in issues[:limit]:
        code = getattr(issue, "code", "") or ""
        message = getattr(issue, "message", "") or ""
        url = getattr(issue, "url", "") or ""
        line = f"[{code}] {message}"
        if url:
            line += f" ({url})"
        _bullet(pdf, line)
    if len(issues) > limit:
        _bullet(pdf, f"...and {len(issues) - limit} more")


def _optimization_section(pdf: Any, optimization: Any) -> None:
    """AI optimize advice — only when stored on the audit (optimize=true)."""
    if optimization is None:
        return
    pages = getattr(optimization, "pages", None) or []
    if not pages and getattr(optimization, "page", None) is not None:
        pages = [optimization.page]
    if not pages:
        status = getattr(optimization, "status", None)
        if status:
            _section(pdf, "Optimize advice")
            _bullet(pdf, f"Status: {status}")
            msg = getattr(optimization, "message", None)
            if msg:
                _bullet(pdf, str(msg))
        return

    _section(pdf, "Optimize advice")
    status = getattr(optimization, "status", None)
    if status:
        _bullet(pdf, f"Status: {status}")
    keywords = list(getattr(optimization, "target_keywords", None) or [])
    if keywords:
        _bullet(pdf, "Target keywords: " + ", ".join(str(k) for k in keywords[:12]))
    disclaimer = (
        "Suggestions only — does not edit the live site. "
        "Included when the audit ran with optimize enabled."
    )
    _bullet(pdf, disclaimer)

    for page in pages[:5]:
        url = getattr(page, "url", "") or ""
        if url:
            _safe_multi(pdf, str(url), size=9, style="B")
        title = getattr(page, "improved_title", None)
        meta = getattr(page, "improved_meta_description", None)
        h1 = getattr(page, "improved_h1", None)
        if title:
            _bullet(pdf, f"Title: {title}")
        if meta:
            _bullet(pdf, f"Meta: {meta}")
        if h1:
            _bullet(pdf, f"H1: {h1}")
        headings = list(getattr(page, "heading_suggestions", None) or [])[:6]
        if headings:
            _bullet(pdf, "Heading ideas: " + "; ".join(str(h) for h in headings))
        kw_sugs = list(getattr(page, "keyword_suggestions", None) or [])[:8]
        if kw_sugs:
            _bullet(pdf, "Keywords: " + ", ".join(str(k) for k in kw_sugs))
        for note in list(getattr(page, "notes", None) or [])[:4]:
            _bullet(pdf, f"Note: {note}")
        faqs = list(getattr(page, "faq_suggestions", None) or [])[:3]
        for faq in faqs:
            q = getattr(faq, "question", None) or (faq.get("question") if isinstance(faq, dict) else None)
            a = getattr(faq, "answer", None) or (faq.get("answer") if isinstance(faq, dict) else None)
            if q:
                _bullet(pdf, f"FAQ: {q}")
            if a:
                _bullet(pdf, f"  A: {a}")
        pdf.ln(1)


def _summary_integrations(pdf: Any, summary: dict[str, Any]) -> None:
    psi = summary.get("pagespeed") or {}
    if psi and psi.get("status") not in (None, "skipped"):
        _section(pdf, "PageSpeed / Core Web Vitals")
        _bullet(pdf, f"Status: {psi.get('status')}")
        for strat in psi.get("strategies") or []:
            lab = strat.get("lab") or {}
            name = strat.get("strategy") or "mobile"
            _bullet(
                pdf,
                (
                    f"{name}: performance {lab.get('performance_score')}/100, "
                    f"LCP {lab.get('lcp_ms')}ms, CLS {lab.get('cls')}"
                ),
            )
        lab = psi.get("lab") or {}
        if lab and not psi.get("strategies"):
            _bullet(
                pdf,
                (
                    f"Performance {lab.get('performance_score')}/100, "
                    f"LCP {lab.get('lcp_ms')}ms, CLS {lab.get('cls')}"
                ),
            )

    gsc = summary.get("google_search_console") or {}
    if gsc and gsc.get("status") not in (None, "skipped"):
        _section(pdf, "Google Search Console")
        _bullet(pdf, f"Status: {gsc.get('status')}")
        if gsc.get("matched_site_url"):
            _bullet(pdf, f"Property: {gsc.get('matched_site_url')}")
        if gsc.get("message"):
            _bullet(pdf, str(gsc.get("message")))
        snap = gsc.get("snapshot") or {}
        if snap:
            n = snap.get("opportunity_count") or len(snap.get("opportunities") or [])
            _bullet(pdf, f"Opportunities: {n}")

    ga4 = summary.get("google_analytics") or {}
    if ga4 and ga4.get("status") not in (None, "skipped"):
        _section(pdf, "Google Analytics (GA4)")
        _bullet(pdf, f"Status: {ga4.get('status')}")
        pid = ga4.get("property_id") or (ga4.get("snapshot") or {}).get("property_id")
        if pid:
            _bullet(pdf, f"Property: {pid}")
        totals = (ga4.get("snapshot") or {}).get("totals") or {}
        if totals:
            _bullet(
                pdf,
                (
                    f"Sessions {totals.get('sessions', 0)} | "
                    f"Users {totals.get('total_users', 0)} | "
                    f"Views {totals.get('screen_page_views', 0)}"
                ),
            )

    serp = summary.get("serp") or {}
    if serp and serp.get("status") not in (None, "skipped"):
        _section(pdf, "SERP / Rankings")
        _bullet(pdf, f"Status: {serp.get('status')}")
        if serp.get("message"):
            _bullet(pdf, str(serp.get("message")))
        if serp.get("target_domain"):
            _bullet(pdf, f"Target domain: {serp.get('target_domain')}")
        for check in (serp.get("checks") or [])[:12]:
            kw = check.get("keyword")
            rank = check.get("rank") or {}
            if rank.get("found"):
                _bullet(
                    pdf,
                    f"{kw} -> position {rank.get('position')} ({rank.get('url')})",
                )
            else:
                _bullet(pdf, f"{kw} -> not in top results")
        if serp.get("organic") and not serp.get("checks"):
            for row in (serp.get("organic") or [])[:8]:
                _bullet(
                    pdf,
                    f"#{row.get('rank_group')} {row.get('domain')} — {row.get('title')}",
                )

    bl = summary.get("backlinks") or {}
    if bl and bl.get("status") not in (None, "skipped"):
        _section(pdf, "Backlinks")
        _bullet(pdf, f"Status: {bl.get('status')}")
        if bl.get("message"):
            _bullet(pdf, str(bl.get("message")))
        snap = bl.get("summary") or {}
        if snap:
            _bullet(pdf, f"Backlinks: {snap.get('backlinks')}")
            _bullet(pdf, f"Referring domains: {snap.get('referring_domains')}")
        for row in (bl.get("top_referring_domains") or [])[:8]:
            _bullet(
                pdf,
                (
                    f"{row.get('domain')} — backlinks {row.get('backlinks')}, "
                    f"rank {row.get('rank')}"
                ),
            )

    kr = summary.get("keyword_research") or {}
    if kr and kr.get("status") not in (None, "skipped", "unavailable"):
        _section(pdf, "Keyword research")
        _bullet(pdf, f"Status: {kr.get('status')}")
        _bullet(pdf, f"Real research: {'yes' if kr.get('is_real_research') else 'no'}")
        if kr.get("message"):
            _bullet(pdf, str(kr.get("message")))
        research = kr.get("research") or {}
        metrics = kr.get("metrics") or research.get("keywords") or []
        if metrics and kr.get("is_real_research"):
            for row in metrics[:12]:
                _bullet(
                    pdf,
                    (
                        f"{row.get('keyword')}: vol {row.get('search_volume', '—')}, "
                        f"KD {row.get('keyword_difficulty', '—')}"
                    ),
                )
