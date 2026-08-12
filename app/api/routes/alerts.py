"""Monitoring alerts status / dry-run."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.alert_service import AlertService

router = APIRouter(tags=["alerts"])


class AlertTestRequest(BaseModel):
    """Optional sample payload to evaluate triggers without a live audit."""

    score: float = 70.0
    seed_url: str = "https://example.com/"
    score_delta: float = -8.0
    has_baseline: bool = True
    new_criticals: list[dict[str, Any]] = Field(default_factory=list)
    deliver: bool = False  # if true and webhook set, actually POST


@router.get("/alerts/status")
def alerts_status():
    return AlertService().status()


@router.post("/alerts/test")
def alerts_test(body: AlertTestRequest):
    """Evaluate triggers (and optionally deliver) with synthetic compare data."""
    svc = AlertService()
    result = {
        "audit_id": "test-alert",
        "seed_url": body.seed_url,
        "score": body.score,
        "summary": {
            "compare": {
                "has_baseline": body.has_baseline,
                "score_delta": body.score_delta,
                "new_issues": len(body.new_criticals),
                "resolved_issues": 0,
            }
        },
        "audit": {
            "diff": {
                "new_issues": [
                    {
                        "code": c.get("code") or "test_critical",
                        "severity": "critical",
                        "message": c.get("message") or "Test critical issue",
                        "url": c.get("url") or body.seed_url,
                    }
                    for c in (body.new_criticals or [{"code": "test_critical"}])
                ]
            }
        },
    }
    triggers = svc.build_triggers(
        result,
        score_drop_threshold=svc.settings.alerts.score_drop_threshold,
        on_new_critical=svc.settings.alerts.on_new_critical,
    )
    if not body.deliver:
        return {
            "status": "ok",
            "fired": False,
            "delivered": False,
            "triggers": triggers,
            "message": "Dry run — set deliver=true to POST the webhook",
            "configured": svc.status()["configured"],
        }
    if not svc.status()["configured"]:
        raise HTTPException(
            status_code=400,
            detail="SEO_ALERT_WEBHOOK_URL is not set",
        )
    out = svc.evaluate_and_notify(result, schedule_id="test")
    return out
