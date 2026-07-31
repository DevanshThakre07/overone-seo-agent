from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_job_runner
from app.api.jobs import JobRunner
from app.api.schemas import AuditRequest, AuditSummaryResponse, JobResponse
from app.logging import get_logger, log_event
from app.tools.audit_tool import audit_site

router = APIRouter(tags=["audit"])
logger = get_logger(__name__)


def _run_audit(payload: AuditRequest) -> dict:
    audit = audit_site(
        str(payload.url),
        max_pages=payload.max_pages,
        max_depth=payload.max_depth,
        save=payload.save or payload.compare,
        compare=payload.compare,
        optimize=payload.optimize,
        target_keywords=payload.target_keywords or None,
        optimize_max_pages=payload.optimize_max_pages,
    )
    return {
        "audit_id": audit.audit_id,
        "seed_url": audit.seed_url,
        "score": audit.score,
        "pages": len(audit.pages),
        "issues": len(audit.issues),
        "summary": audit.summary,
        "status": "completed",
        "audit": audit.model_dump(mode="json"),
    }


@router.post("/audit", response_model=AuditSummaryResponse)
def create_audit(
    payload: AuditRequest,
    jobs: JobRunner = Depends(get_job_runner),
) -> AuditSummaryResponse:
    log_event(logger, "api_audit_requested", url=str(payload.url), background=payload.background)

    if payload.background:
        job_id = jobs.submit(_run_audit, payload, result_type="audit")
        return AuditSummaryResponse(
            audit_id="",
            seed_url=str(payload.url),
            score=0.0,
            pages=0,
            issues=0,
            job_id=job_id,
            status="accepted",
            summary={"message": "Audit started in background. Poll GET /jobs/{job_id}."},
        )

    try:
        result = _run_audit(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AuditSummaryResponse(
        audit_id=result["audit_id"],
        seed_url=result["seed_url"],
        score=result["score"],
        pages=result["pages"],
        issues=result["issues"],
        summary=result["summary"],
        status="completed",
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, jobs: JobRunner = Depends(get_job_runner)) -> JobResponse:
    record = jobs.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    result = record.result
    # Avoid returning huge nested audit blobs by default in job poll;
    # keep summary fields if present.
    slim = None
    if result is not None:
        slim = {
            k: result[k]
            for k in ("audit_id", "seed_url", "score", "pages", "issues", "summary", "status")
            if k in result
        }
        if "audit_id" in result:
            slim["audit_id"] = result["audit_id"]

    return JobResponse(
        job_id=record.job_id,
        status=record.status.value,
        result_type=record.result_type,
        result=slim,
        error=record.error,
    )
