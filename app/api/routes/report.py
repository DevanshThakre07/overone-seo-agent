from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from app.api.dependencies import get_report_service
from app.api.schemas import ReportRequest
from app.logging import get_logger, log_event
from app.models.reports import ReportFormat
from app.services.report_service import ReportService
from app.tools.report_tool import generate_report

router = APIRouter(tags=["report"])
logger = get_logger(__name__)


def _pdf_filename(audit_id: str, seed_url: str | None = None) -> str:
    host = "report"
    if seed_url:
        try:
            from urllib.parse import urlparse

            host = (urlparse(seed_url).hostname or "report").replace(".", "-")
        except Exception:  # noqa: BLE001
            host = "report"
    return f"seo-report-{host}-{audit_id[:8]}.pdf"


@router.post("/report")
def create_report(payload: ReportRequest) -> dict:
    if payload.url is None and payload.audit_id is None:
        raise HTTPException(status_code=400, detail="url or audit_id is required")

    log_event(
        logger,
        "api_report_requested",
        url=str(payload.url) if payload.url else None,
        audit_id=payload.audit_id,
        format=payload.format,
    )
    try:
        artifact = generate_report(
            url=str(payload.url) if payload.url else None,
            audit_id=payload.audit_id,
            format=payload.format,
            max_pages=payload.max_pages,
            save=payload.save,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if artifact.format == ReportFormat.PDF:
        return {
            "audit_id": artifact.audit_id,
            "format": "pdf",
            "content_base64": artifact.content,
            "media_type": "application/pdf",
            "path": artifact.path,
            "metadata": artifact.metadata,
        }

    return {
        "audit_id": artifact.audit_id,
        "format": artifact.format.value,
        "content": artifact.content,
        "path": artifact.path,
        "metadata": artifact.metadata,
    }


@router.get("/report/{audit_id}")
def get_report(
    audit_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|json|pdf)$"),
    report_service: ReportService = Depends(get_report_service),
):
    log_event(logger, "api_report_get", audit_id=audit_id, format=format)
    try:
        fmt = ReportFormat(format.lower())
        artifact = report_service.generate_from_audit_id(audit_id, fmt)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if fmt == ReportFormat.MARKDOWN:
        return PlainTextResponse(artifact.content, media_type="text/markdown")
    if fmt == ReportFormat.PDF:
        raw = report_service.pdf_bytes(artifact)
        filename = _pdf_filename(
            artifact.audit_id, artifact.metadata.get("seed_url")
        )
        return Response(
            content=raw,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    return {
        "audit_id": artifact.audit_id,
        "format": artifact.format.value,
        "content": artifact.content,
        "metadata": artifact.metadata,
    }
