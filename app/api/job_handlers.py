"""Serializable job handlers for the durable queue."""

from __future__ import annotations

from typing import Any

from app.api.schemas import AuditRequest
from app.tools.audit_tool import audit_site


def run_audit_job(request: dict[str, Any]) -> dict[str, Any]:
    """Execute an audit from a JSON-serializable request dict."""
    payload = AuditRequest.model_validate(request)
    audit = audit_site(
        str(payload.url),
        max_pages=payload.max_pages,
        max_depth=payload.max_depth,
        save=payload.save or payload.compare,
        compare=payload.compare,
        optimize=payload.optimize,
        target_keywords=payload.target_keywords or None,
        optimize_max_pages=payload.optimize_max_pages,
        gsc_account_id=payload.gsc_account_id,
        pagespeed=payload.pagespeed,
        auth_cookie=payload.auth_cookie,
        auth_headers=payload.auth_headers or None,
        use_authenticated_crawl=payload.use_authenticated_crawl,
        include_serp=payload.include_serp,
        include_backlinks=payload.include_backlinks,
        include_ga4=payload.include_ga4,
        ga4_property_id=payload.ga4_property_id,
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


def dispatch_job(payload: dict[str, Any]) -> dict[str, Any]:
    handler = payload.get("handler") or "audit"
    request = payload.get("request") or {}
    if handler == "audit":
        return run_audit_job(request)
    raise ValueError(f"Unknown job handler: {handler}")


def finalize_schedule_from_job(
    payload: dict[str, Any] | None,
    *,
    audit_id: str | None = None,
    error: str | None = None,
) -> None:
    """When a scheduled audit job finishes, write last_audit_id / last_error."""
    schedule_id = (payload or {}).get("schedule_id")
    if not schedule_id:
        return
    from app.repositories.factory import get_schedule_repository

    get_schedule_repository().set_last_result(
        schedule_id,
        audit_id=audit_id,
        error=(error[:500] if error else None),
    )
