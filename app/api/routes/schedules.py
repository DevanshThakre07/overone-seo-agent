"""Recurring audit schedules."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl

from app.api.principals import get_principal, require_account_access
from app.services.schedule_service import ScheduleService
from app.services.scheduler_runner import scheduler_status

router = APIRouter(tags=["schedules"])


class ScheduleCreate(BaseModel):
    url: HttpUrl
    every_hours: int = Field(24, ge=1, le=24 * 30)
    max_pages: int | None = None
    gsc_account_id: str | None = None
    pagespeed: bool | None = None


class ScheduleEnabled(BaseModel):
    enabled: bool


def _assert_schedule_row(request: Request, row: dict | None) -> None:
    if row is None:
        return
    principal = get_principal(request)
    if principal is None or principal.role == "admin":
        return
    # Clients only manage schedules tagged with their account_id.
    require_account_access(request, row.get("gsc_account_id"))
    if (row.get("gsc_account_id") or "").strip() != (principal.account_id or ""):
        raise HTTPException(status_code=403, detail="Schedule belongs to another client")


@router.get("/schedules/status")
def get_scheduler_status():
    return scheduler_status()


@router.get("/schedules")
def list_schedules(request: Request):
    rows = ScheduleService().list_schedules()
    principal = get_principal(request)
    if principal is not None and principal.role == "client":
        rows = [
            r
            for r in rows
            if (r.get("gsc_account_id") or "").strip() == (principal.account_id or "")
        ]
    return {"schedules": rows}


@router.post("/schedules")
def create_schedule(request: Request, payload: ScheduleCreate):
    principal = get_principal(request)
    gsc_id = payload.gsc_account_id
    if principal is not None and principal.role == "client":
        # Bind schedule to the caller's account (ignore spoofed ids).
        gsc_id = principal.account_id
    else:
        require_account_access(request, gsc_id)
    row = ScheduleService().create(
        str(payload.url),
        every_hours=payload.every_hours,
        max_pages=payload.max_pages,
        gsc_account_id=gsc_id,
        pagespeed=payload.pagespeed,
    )
    return row


@router.post("/schedules/{schedule_id}/enabled")
def enable_schedule(request: Request, schedule_id: str, payload: ScheduleEnabled):
    svc = ScheduleService()
    existing = next(
        (r for r in svc.list_schedules() if r.get("schedule_id") == schedule_id),
        None,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    _assert_schedule_row(request, existing)
    row = svc.set_enabled(schedule_id, payload.enabled)
    if row is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return row


@router.delete("/schedules/{schedule_id}")
def delete_schedule(request: Request, schedule_id: str):
    svc = ScheduleService()
    existing = next(
        (r for r in svc.list_schedules() if r.get("schedule_id") == schedule_id),
        None,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    _assert_schedule_row(request, existing)
    if not svc.delete(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted", "schedule_id": schedule_id}


@router.post("/schedules/run-due")
def run_due_now(request: Request):
    """Manual tick — useful for local testing without waiting for the poller."""
    principal = get_principal(request)
    if principal is not None and principal.role == "client":
        raise HTTPException(
            status_code=403,
            detail="Only admin API keys can trigger run-due.",
        )
    results = ScheduleService().run_due()
    return {"ran": len(results), "results": results}
