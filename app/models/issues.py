from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Issue(BaseModel):
    code: str
    severity: Severity
    message: str
    url: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AnalyzerResult(BaseModel):
    analyzer: str
    issues: list[Issue] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
