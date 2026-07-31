"""JobRunner interface — in-process now; swap for Celery/RQ later."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable


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


class InProcessJobRunner:
    """Simple background runner using a thread pool."""

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

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
