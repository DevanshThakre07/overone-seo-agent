"""Background thread that polls due audit schedules while seo-api is up."""

from __future__ import annotations

import threading
import time
from typing import Any

from app.logging import get_logger, log_event
from app.services.schedule_service import ScheduleService

logger = get_logger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None
_POLL_SECONDS = 60


def start_scheduler(*, poll_seconds: int = _POLL_SECONDS) -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()

    def _loop() -> None:
        log_event(logger, "scheduler_started", poll_seconds=poll_seconds)
        # Small delay so API can finish boot before first poll.
        time.sleep(2)
        while not _stop.is_set():
            try:
                results = ScheduleService().run_due()
                if results:
                    log_event(
                        logger,
                        "scheduler_tick",
                        ran=len(results),
                        ok=sum(1 for r in results if r.get("status") == "ok"),
                    )
            except Exception as exc:  # noqa: BLE001
                log_event(logger, "scheduler_tick_error", error=str(exc))
            _stop.wait(poll_seconds)
        log_event(logger, "scheduler_stopped")

    _thread = threading.Thread(target=_loop, name="seo-schedule-runner", daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()


def scheduler_status() -> dict[str, Any]:
    alive = _thread is not None and _thread.is_alive()
    return {
        "running": alive,
        "poll_seconds": _POLL_SECONDS,
        "message": (
            "Schedule runner active inside seo-api."
            if alive
            else "Schedule runner not running (start seo-api)."
        ),
    }
