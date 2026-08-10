"""Durable job store protocol (SQLite or Postgres)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.api.jobs import JobRecord


@runtime_checkable
class JobStore(Protocol):
    def enqueue(self, *, result_type: str, payload: dict[str, Any]) -> str: ...

    def get(self, job_id: str) -> JobRecord | None: ...

    def claim_next(
        self, *, worker_id: str, lease_seconds: int = 3600
    ) -> JobRecord | None: ...

    def complete(self, job_id: str, result: dict[str, Any]) -> None: ...

    def fail(self, job_id: str, error: str) -> None: ...

    def reclaim_stale(self, *, older_than_seconds: int = 3600) -> int: ...
