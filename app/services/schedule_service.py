"""Create/list schedules and enqueue due audits onto the durable job queue."""

from __future__ import annotations

from typing import Any

from app.api.dependencies import get_job_runner
from app.config.settings import Settings, get_settings
from app.logging import get_logger, log_event
from app.repositories.factory import get_schedule_repository

logger = get_logger(__name__)


class ScheduleService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = get_schedule_repository(self.settings)

    def create(
        self,
        url: str,
        *,
        every_hours: int = 24,
        max_pages: int | None = None,
        gsc_account_id: str | None = None,
        pagespeed: bool | None = None,
    ) -> dict[str, Any]:
        row = self.repo.create(
            url,
            every_hours=every_hours,
            max_pages=max_pages,
            gsc_account_id=gsc_account_id,
            pagespeed=pagespeed,
        )
        log_event(
            logger,
            "schedule_created",
            schedule_id=row["schedule_id"],
            url=row["seed_url"],
            every_hours=row["every_hours"],
        )
        return row

    def list_schedules(self) -> list[dict[str, Any]]:
        return self.repo.list_all()

    def delete(self, schedule_id: str) -> bool:
        return self.repo.delete(schedule_id)

    def set_enabled(self, schedule_id: str, enabled: bool) -> dict[str, Any] | None:
        return self.repo.set_enabled(schedule_id, enabled)

    def run_due(self) -> list[dict[str, Any]]:
        """Enqueue durable jobs for all due schedules; returns per-run results."""
        due = self.repo.due()
        results: list[dict[str, Any]] = []
        for sched in due:
            results.append(self._enqueue_one(sched))
        return results

    def _enqueue_one(self, sched: dict[str, Any]) -> dict[str, Any]:
        schedule_id = sched["schedule_id"]
        url = sched["seed_url"]
        request = {
            "url": url,
            "max_pages": sched.get("max_pages"),
            "save": True,
            "compare": True,
            "gsc_account_id": sched.get("gsc_account_id"),
            "pagespeed": sched.get("pagespeed"),
        }
        try:
            job_id = get_job_runner().enqueue_audit(
                request,
                schedule_id=schedule_id,
            )
            self.repo.mark_enqueued(schedule_id, job_id=job_id)
            log_event(
                logger,
                "schedule_enqueued",
                schedule_id=schedule_id,
                job_id=job_id,
            )
            return {
                "schedule_id": schedule_id,
                "status": "queued",
                "job_id": job_id,
            }
        except Exception as exc:  # noqa: BLE001
            self.repo.mark_run(schedule_id, audit_id=None, error=str(exc)[:500])
            log_event(
                logger,
                "schedule_enqueue_failed",
                schedule_id=schedule_id,
                error=str(exc),
            )
            return {
                "schedule_id": schedule_id,
                "status": "error",
                "message": str(exc),
            }
