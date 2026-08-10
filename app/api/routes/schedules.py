"""Recurring audit schedules."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

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


@router.get("/schedules/status")
def get_scheduler_status():
    return scheduler_status()


@router.get("/schedules")
def list_schedules():
    return {"schedules": ScheduleService().list_schedules()}


@router.post("/schedules")
def create_schedule(payload: ScheduleCreate):
    row = ScheduleService().create(
        str(payload.url),
        every_hours=payload.every_hours,
        max_pages=payload.max_pages,
        gsc_account_id=payload.gsc_account_id,
        pagespeed=payload.pagespeed,
    )
    return row


@router.post("/schedules/{schedule_id}/enabled")
def enable_schedule(schedule_id: str, payload: ScheduleEnabled):
    row = ScheduleService().set_enabled(schedule_id, payload.enabled)
    if row is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return row


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str):
    if not ScheduleService().delete(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted", "schedule_id": schedule_id}


@router.post("/schedules/run-due")
def run_due_now():
    """Manual tick — useful for local testing without waiting for the poller."""
    results = ScheduleService().run_due()
    return {"ran": len(results), "results": results}
