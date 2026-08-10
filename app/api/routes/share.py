"""Public shareable report links."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.models.reports import ReportFormat
from app.repositories.factory import get_audit_repository, get_share_repository
from app.reports.markdown_report import render_markdown
from app.reports.pdf_report import PdfNotImplementedError, render_pdf

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
            "Public share created. Open GET /share/{token} (HTML), "
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

    md = render_markdown(audit)
    if format == "markdown":
        return {
            "audit_id": audit.audit_id,
            "seed_url": audit.seed_url,
            "score": audit.score,
            "format": "markdown",
            "content": md,
            "expires_at": record.get("expires_at"),
            "pdf_url": f"/share/{token}?format=pdf",
        }

    escaped = (
        md.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SEO Report — {audit.seed_url}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      margin: 0; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: #f6f3ee; color: #1c1a17; line-height: 1.55;
    }}
    header {{
      padding: 1.5rem 1.25rem; background: #1c1a17; color: #f6f3ee;
    }}
    header h1 {{ margin: 0; font-size: 1.15rem; font-weight: 600; }}
    header p {{ margin: 0.35rem 0 0; opacity: 0.75; font-size: 0.9rem; }}
    header a {{
      color: #d7ebe3; margin-left: 0.75rem; font-size: 0.9rem;
    }}
    main {{
      max-width: 52rem; margin: 0 auto; padding: 1.5rem 1.25rem 3rem;
    }}
    pre {{
      white-space: pre-wrap; word-break: break-word;
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.88rem; background: #fff; border: 1px solid #ddd4c8;
      padding: 1.25rem; border-radius: 2px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>SEO Report</h1>
    <p>
      {audit.seed_url} · score {audit.score} · expires {record.get("expires_at")}
      <a href="/share/{token}?format=pdf">Download PDF</a>
      <a href="/share/{token}?format=markdown">Markdown</a>
    </p>
  </header>
  <main><pre>{escaped}</pre></main>
</body>
</html>"""
    return HTMLResponse(html)
