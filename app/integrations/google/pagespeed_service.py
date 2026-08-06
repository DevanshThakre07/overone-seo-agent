"""PageSpeed Insights service used by audits and API routes."""

from __future__ import annotations

from typing import Any

from app.config.settings import Settings, get_settings
from app.integrations.google.pagespeed import PageSpeedClient, PageSpeedError
from app.logging import get_logger, log_event
from app.models.issues import Issue

logger = get_logger(__name__)


class PageSpeedService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = PageSpeedClient(self.settings.pagespeed)

    def is_configured(self) -> bool:
        return self.client.is_configured()

    def analyze(self, url: str) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "skipped",
                "url": url,
                "message": (
                    "PageSpeed Insights is not configured. Set GOOGLE_PAGESPEED_API_KEY "
                    "and enable the PageSpeed Insights API in Google Cloud."
                ),
                "issues": [],
                "issue_objects": [],
            }
        try:
            result = self.client.analyze_url(url)
            log_event(
                logger,
                "pagespeed_completed",
                url=url,
                status=result.get("status"),
                strategies=len(result.get("strategies") or []),
                issues=len(result.get("issue_objects") or []),
            )
            return result
        except PageSpeedError as exc:
            log_event(logger, "pagespeed_failed", url=url, error=str(exc))
            return {
                "status": "error",
                "url": url,
                "message": str(exc),
                "issues": [],
                "issue_objects": [],
            }

    def audit_enrichment(
        self, url: str, *, run: bool = True
    ) -> tuple[dict[str, Any], list[Issue]]:
        """Return summary block + issues to merge into the audit.

        Never raises — audits must succeed even when PSI is down.
        """
        if not run:
            return (
                {
                    "status": "skipped",
                    "message": "PageSpeed was disabled for this audit (pagespeed=false).",
                },
                [],
            )
        result = self.analyze(url)
        issues: list[Issue] = list(result.pop("issue_objects", []) or [])
        # Keep JSON-serializable issues in the summary too.
        if "issues" not in result:
            result["issues"] = [i.model_dump(mode="json") for i in issues]
        return result, issues
