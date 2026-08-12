"""JobRunner — in-process (tests) and durable DB-backed queue (default)."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from app.logging import get_logger, log_event

logger = get_logger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    result_type: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    payload: dict[str, Any] | None = None
    _future: Future[Any] | None = field(default=None, repr=False)


@runtime_checkable
class JobRunner(Protocol):
    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        result_type: str = "generic",
        **kwargs: Any,
    ) -> str: ...

    def get(self, job_id: str) -> JobRecord | None: ...

    def enqueue_audit(
        self,
        request: dict[str, Any],
        *,
        schedule_id: str | None = None,
    ) -> str: ...


class InProcessJobRunner:
    """Simple background runner using a thread pool (tests / non-durable)."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        result_type: str = "generic",
        **kwargs: Any,
    ) -> str:
        job_id = str(uuid.uuid4())
        record = JobRecord(job_id=job_id, status=JobStatus.PENDING, result_type=result_type)

        def _wrapped() -> Any:
            with self._lock:
                record.status = JobStatus.RUNNING
            try:
                value = fn(*args, **kwargs)
                payload = value if isinstance(value, dict) else {"value": value}
                with self._lock:
                    record.status = JobStatus.COMPLETED
                    record.result = payload
                return value
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    record.status = JobStatus.FAILED
                    record.error = str(exc)
                raise

        with self._lock:
            self._jobs[job_id] = record
        record._future = self._executor.submit(_wrapped)
        return job_id

    def enqueue_audit(
        self,
        request: dict[str, Any],
        *,
        schedule_id: str | None = None,
    ) -> str:
        from app.api.job_handlers import finalize_schedule_from_job, run_audit_job

        def _run() -> dict[str, Any]:
            try:
                result = run_audit_job(request)
                from app.api.job_handlers import after_audit_job_success

                after_audit_job_success(
                    result,
                    {"schedule_id": schedule_id} if schedule_id else {},
                    schedule_id=schedule_id,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                finalize_schedule_from_job(
                    {"schedule_id": schedule_id} if schedule_id else {},
                    error=str(exc),
                )
                raise

        return self.submit(_run, result_type="audit")

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def start(self) -> None:
        """No-op — workers are the thread pool."""

    def stop(self) -> None:
        self.shutdown()


class DurableJobRunner:
    """DB-backed queue with claim/lease workers (survives process restart)."""

    def __init__(
        self,
        store: Any,
        *,
        max_workers: int = 2,
        poll_seconds: float = 0.5,
        lease_seconds: int = 3600,
    ) -> None:
        self._store = store
        self._max_workers = max(1, max_workers)
        self._poll_seconds = poll_seconds
        self._lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._started = False
        self._lock = threading.Lock()

    def enqueue_audit(
        self,
        request: dict[str, Any],
        *,
        schedule_id: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {"handler": "audit", "request": request}
        if schedule_id:
            payload["schedule_id"] = schedule_id
        return self._store.enqueue(result_type="audit", payload=payload)

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        result_type: str = "generic",
        **kwargs: Any,
    ) -> str:
        """Best-effort: only audit jobs are durable; others run in-thread after enqueue fail."""
        # Prefer serializable audit path when args look like AuditRequest / dict.
        if result_type == "audit" and args:
            first = args[0]
            if isinstance(first, dict):
                return self.enqueue_audit(first)
            if hasattr(first, "model_dump"):
                return self.enqueue_audit(first.model_dump(mode="json"))
        raise TypeError(
            "DurableJobRunner only supports enqueue_audit / audit submits. "
            "Use InProcessJobRunner for arbitrary callables."
        )

    def get(self, job_id: str) -> JobRecord | None:
        return self._store.get(job_id)

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._stop.clear()
            reclaimed = self._store.reclaim_stale(older_than_seconds=self._lease_seconds)
            if reclaimed:
                log_event(logger, "jobs_reclaimed_stale", count=reclaimed)
            for i in range(self._max_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"seo-job-worker-{i}",
                    daemon=True,
                    args=(f"worker-{i}",),
                )
                t.start()
                self._threads.append(t)
            self._started = True
            log_event(logger, "job_runner_started", workers=self._max_workers)

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            threads = list(self._threads)
            self._threads.clear()
            self._started = False
        for t in threads:
            t.join(timeout=2.0)
        log_event(logger, "job_runner_stopped")

    def shutdown(self) -> None:
        self.stop()

    def _worker_loop(self, worker_id: str) -> None:
        from app.api.job_handlers import dispatch_job

        while not self._stop.is_set():
            try:
                job = self._store.claim_next(
                    worker_id=worker_id,
                    lease_seconds=self._lease_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                log_event(logger, "job_claim_error", error=str(exc))
                self._stop.wait(self._poll_seconds)
                continue

            if job is None:
                self._stop.wait(self._poll_seconds)
                continue

            try:
                result = dispatch_job(job.payload or {})
                # Persist slim result for poll; full audit stays in audits table when saved.
                slim = {
                    k: result[k]
                    for k in (
                        "audit_id",
                        "seed_url",
                        "score",
                        "pages",
                        "issues",
                        "summary",
                        "status",
                    )
                    if k in result
                }
                self._store.complete(job.job_id, slim)
                from app.api.job_handlers import after_audit_job_success

                after_audit_job_success(
                    result,
                    job.payload,
                    schedule_id=(job.payload or {}).get("schedule_id"),
                    job_id=job.job_id,
                )
                log_event(
                    logger,
                    "job_completed",
                    job_id=job.job_id,
                    result_type=job.result_type,
                )
            except Exception as exc:  # noqa: BLE001
                self._store.fail(job.job_id, str(exc))
                from app.api.job_handlers import finalize_schedule_from_job

                finalize_schedule_from_job(job.payload, error=str(exc))
                log_event(
                    logger,
                    "job_failed",
                    job_id=job.job_id,
                    error=str(exc),
                )
