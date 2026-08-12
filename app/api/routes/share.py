"""Public shareable report links."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.repositories.factory import get_audit_repository, get_share_repository
from app.reports.markdown_report import render_markdown
from app.reports.pdf_report import PdfNotImplementedError, render_pdf
from app.reports.scorecard_html import render_scorecard_html

router = APIRouter(tags=["share"])


class ShareCreate(BaseModel):
    days_valid: int = Field(30, ge=1, le=365)


@router.post("/report/{audit_id}/share")
def create_share(audit_id: str, payload: ShareCreate | None = None):
    settings = get_settings()
    audit = get_audit_repository(settings).get(audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail=f"Audit not found: {audit_id}")
    days = (payload.days_valid if payload else 30)
    share = get_share_repository(settings).create(audit_id, days_valid=days)
    token = share.get("token")
    return {
        **share,
        "html_url": f"/share/{token}",
        "pdf_url": f"/share/{token}?format=pdf",
        "markdown_url": f"/share/{token}?format=markdown",
        "message": (
            "Public client scorecard created. Open GET /share/{token} (HTML scorecard), "
            "or ?format=pdf / ?format=markdown (no API key required)."
        ),
    }


@router.get("/share/{token}")
def view_share(
    token: str,
    format: str = Query(default="html", pattern="^(html|markdown|pdf)$"),
):
    settings = get_settings()
    share_repo = get_share_repository(settings)
    record = share_repo.get(token)
    if record is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    if record.get("expired"):
        raise HTTPException(status_code=410, detail="Share link expired")
    audit = get_audit_repository(settings).get(record["audit_id"])
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit no longer available")

    if format == "pdf":
        try:
            raw = render_pdf(audit)
        except PdfNotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        filename = f"seo-report-{audit.audit_id[:8]}.pdf"
        return Response(
            content=raw,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    if format == "markdown":
        md = render_markdown(audit)
        return {
            "audit_id": audit.audit_id,
            "seed_url": audit.seed_url,
            "score": audit.score,
            "format": "markdown",
            "content": md,
            "expires_at": record.get("expires_at"),
            "pdf_url": f"/share/{token}?format=pdf",
        }

    # Default HTML = thin client scorecard (FP-4). Full markdown via ?format=markdown.
    return HTMLResponse(
        render_scorecard_html(
            audit,
            token=token,
            expires_at=record.get("expires_at"),
        )
    )
