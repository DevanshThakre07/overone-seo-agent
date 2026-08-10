"""Build a normalized ReportDocument from a SiteAudit."""

from __future__ import annotations

from collections import Counter

from app.analyzers.recommendations import build_prescriptive_recommendations
from app.models.audit import SiteAudit
from app.models.issues import Severity
from app.models.reports import ReportDocument, ReportSummary


def build_report_document(audit: SiteAudit) -> ReportDocument:
    critical = [i for i in audit.issues if i.severity == Severity.CRITICAL]
    warnings = [i for i in audit.issues if i.severity == Severity.WARNING]
    suggestions = [i for i in audit.issues if i.severity == Severity.INFO]

    code_counts = Counter(i.code for i in audit.issues)
    top_codes = [code for code, _ in code_counts.most_common(5)]

    scope = (audit.summary or {}).get("scope") or {
        "seed_url": audit.seed_url,
        "pages_analyzed": len(audit.pages),
        "note": (
            f"This audit analyzed {len(audit.pages)} page(s) starting from "
            f"{audit.seed_url}."
        ),
    }
    rendering = (audit.summary or {}).get("rendering") or {}
    recommendations = (audit.summary or {}).get("recommendations")
    if recommendations is None:
        recommendations = build_prescriptive_recommendations(audit.pages)

    notes: list[str] = [scope.get("note") or ""]
    notes = [n for n in notes if n]
    if rendering.get("rendering_incomplete"):
        notes.insert(
            0,
            rendering.get("warning")
            or "Rendering incomplete — client-rendered DOM was not captured; content findings are unreliable.",
        )
    if audit.optimization is not None:
        notes.append(f"AI optimization status: {audit.optimization.status}")
        if audit.optimization.message:
            notes.append(audit.optimization.message)
        kr = audit.optimization.keyword_research or {}
        if kr.get("status") and kr.get("status") != "caller_provided":
            notes.append(
                kr.get("research", {}).get("message")
                or kr.get("message")
                or "Keyword research API is not configured."
            )
    if audit.diff is not None:
        notes.append(audit.diff.summary or "Comparison completed.")

    gsc = (audit.summary or {}).get("google_search_console") or {}
    if gsc.get("status") == "ok":
        snap = gsc.get("snapshot") or {}
        n_opp = int(snap.get("opportunity_count") or len(snap.get("opportunities") or []))
        notes.append(
            f"Google Search Console: {n_opp} opportunit"
            f"{'y' if n_opp == 1 else 'ies'} merged into recommendations "
            f"(site {snap.get('site_url') or gsc.get('site_url') or 'matched'})."
        )
    elif gsc.get("status") not in (None, "skipped") and gsc.get("message"):
        notes.append(f"Google Search Console: {gsc.get('message')}")

    page_overview = [
        {
            "url": page.final_url,
            "status_code": page.status_code,
            "title": page.title,
            "title_source": page.title_source,
            "title_length": len(page.title) if page.title else 0,
            "meta_description": page.meta_description,
            "meta_description_length": (
                len(page.meta_description) if page.meta_description else 0
            ),
            "is_broken": page.is_broken,
            "h1": page.h1,
            "h1_count": len(page.h1),
            "h2_count": len(page.h2),
            "h3_count": len(page.h3),
            "image_count": page.image_count or len(page.images),
            "images_missing_alt": sum(
                1
                for img in page.images
                if (not img.alt_present)
                and (not img.decorative)
                and (not getattr(img, "is_source", False))
            ),
            "internal_links": len(page.internal_links),
            "internal_link_occurrences": page.internal_link_occurrences,
            "external_links": len(page.external_links),
            "external_link_occurrences": page.external_link_occurrences,
            "word_count": page.word_count,
            "canonical": page.canonical,
            "has_json_ld": page.has_json_ld,
            "schema_types": page.schema_types,
            "js_rendered": page.js_rendered,
            "extraction_warnings": page.extraction_warnings,
        }
        for page in audit.pages
    ]

    score_note = (audit.summary or {}).get("score_note")
    if score_note:
        notes.insert(0, score_note)

    summary = ReportSummary(
        seed_url=audit.seed_url,
        audit_id=audit.audit_id,
        created_at=audit.created_at,
        pages_analyzed=len(audit.pages),
        overall_seo_score=audit.score,
        critical_count=len(critical),
        warning_count=len(warnings),
        suggestion_count=len(suggestions),
        top_issue_codes=top_codes,
        notes=notes,
        scope_note=scope.get("note") or "",
        rendering_warning=(
            rendering.get("warning")
            if rendering.get("rendering_incomplete")
            else None
        ),
        score_note=score_note,
        scoring_mode_note=((audit.summary or {}).get("score_breakdown") or {}).get(
            "scoring_mode_note"
        ),
    )

    return ReportDocument(
        summary=summary,
        critical_issues=critical,
        warnings=warnings,
        suggestions=suggestions,
        recommendations=recommendations,
        overall_seo_score=audit.score,
        optimization=audit.optimization,
        diff=audit.diff,
        page_overview=page_overview,
        scope=scope,
    )
