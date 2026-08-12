"""Monitoring alerts — webhook when score drops or new criticals appear."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config.settings import Settings, get_settings
from app.logging import get_logger, log_event

logger = get_logger(__name__)


class AlertService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def status(self) -> dict[str, Any]:
        a = self.settings.alerts
        url = (a.webhook_url or "").strip()
        return {
            "configured": bool(url),
            "webhook_url_set": bool(url),
            "score_drop_threshold": a.score_drop_threshold,
            "on_new_critical": a.on_new_critical,
            "timeout_seconds": a.timeout_seconds,
            "message": (
                "Alerts ready — POST JSON to SEO_ALERT_WEBHOOK_URL when "
                "scheduled/compare audits regress."
                if url
                else (
                    "Set SEO_ALERT_WEBHOOK_URL to receive score-drop / "
                    "new-critical notifications (Slack/Discord/custom)."
                )
            ),
        }

    def evaluate_and_notify(
        self,
        result: dict[str, Any],
        *,
        schedule_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Inspect audit job result; POST webhook if triggers fire.

        Safe to call always — no-ops when webhook unset or nothing triggered.
        """
        a = self.settings.alerts
        webhook = (a.webhook_url or "").strip()
        if not webhook:
            return {"status": "skipped", "reason": "webhook_not_configured"}

        triggers = self.build_triggers(
            result,
            score_drop_threshold=a.score_drop_threshold,
            on_new_critical=a.on_new_critical,
        )
        if not triggers:
            return {"status": "ok", "fired": False, "triggers": []}

        payload = {
            "event": "seo_alert",
            "triggers": triggers,
            "audit_id": result.get("audit_id"),
            "seed_url": result.get("seed_url"),
            "score": result.get("score"),
            "schedule_id": schedule_id,
            "job_id": job_id,
            "compare": (result.get("summary") or {}).get("compare") or {},
            "new_criticals": [
                t for t in triggers if t.get("type") == "new_critical"
            ],
            "message": self._human_message(result, triggers),
        }
        delivery = self._post_webhook(webhook, payload, timeout=a.timeout_seconds)
        log_event(
            logger,
            "alert_fired" if delivery.get("ok") else "alert_delivery_failed",
            audit_id=result.get("audit_id"),
            schedule_id=schedule_id,
            triggers=[t.get("type") for t in triggers],
            http_status=delivery.get("status_code"),
            error=delivery.get("error"),
        )
        return {
            "status": "ok" if delivery.get("ok") else "error",
            "fired": True,
            "triggers": triggers,
            "delivery": delivery,
            "payload": payload,
        }

    def build_triggers(
        self,
        result: dict[str, Any],
        *,
        score_drop_threshold: float = 5.0,
        on_new_critical: bool = True,
    ) -> list[dict[str, Any]]:
        triggers: list[dict[str, Any]] = []
        summary = result.get("summary") or {}
        compare = summary.get("compare") or {}
        delta = compare.get("score_delta")
        if (
            compare.get("has_baseline")
            and delta is not None
            and float(delta) <= -abs(float(score_drop_threshold))
        ):
            triggers.append(
                {
                    "type": "score_drop",
                    "score_delta": float(delta),
                    "threshold": float(score_drop_threshold),
                    "score": result.get("score"),
                    "message": (
                        f"Score dropped by {abs(float(delta)):.1f} "
                        f"(now {result.get('score')})"
                    ),
                }
            )

        if on_new_critical:
            criticals = self._new_critical_issues(result)
            for issue in criticals[:20]:
                triggers.append(
                    {
                        "type": "new_critical",
                        "code": issue.get("code"),
                        "message": issue.get("message"),
                        "url": issue.get("url"),
                    }
                )
        return triggers

    def _new_critical_issues(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        audit = result.get("audit") or {}
        diff = audit.get("diff") or {}
        new_issues = diff.get("new_issues") or []
        out: list[dict[str, Any]] = []
        for issue in new_issues:
            sev = str(issue.get("severity") or "").lower()
            if sev == "critical" or sev.endswith(".critical"):
                out.append(issue)
        # Fallback: summary only has counts — no codes
        if not out and not new_issues:
            compare = (result.get("summary") or {}).get("compare") or {}
            n = int(compare.get("new_issues") or 0)
            # Without codes we can't know severity; skip unless we have audit issues
            # and compare says new — leave empty to avoid false alarms.
            _ = n
        return out

    def _human_message(
        self, result: dict[str, Any], triggers: list[dict[str, Any]]
    ) -> str:
        url = result.get("seed_url") or "site"
        parts = [t.get("message") or t.get("code") or t.get("type") for t in triggers]
        return f"SEO alert for {url}: " + "; ".join(str(p) for p in parts if p)

    def _post_webhook(
        self, url: str, payload: dict[str, Any], *, timeout: float
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SEO-Agent-Alerts/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return {
                    "ok": 200 <= getattr(resp, "status", 200) < 300,
                    "status_code": getattr(resp, "status", 200),
                }
        except HTTPError as exc:
            return {"ok": False, "status_code": exc.code, "error": str(exc)}
        except URLError as exc:
            return {"ok": False, "status_code": None, "error": str(exc.reason or exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status_code": None, "error": str(exc)}


def maybe_alert_after_job(
    result: dict[str, Any],
    *,
    schedule_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any] | None:
    """Best-effort alert hook — never raises into the job worker."""
    try:
        return AlertService().evaluate_and_notify(
            result, schedule_id=schedule_id, job_id=job_id
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "alert_hook_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}
