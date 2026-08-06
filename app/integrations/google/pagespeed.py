"""Google PageSpeed Insights API client (Core Web Vitals + Lighthouse)."""

from __future__ import annotations

from typing import Any

import requests

from app.config.settings import PageSpeedSettings
from app.models.issues import Issue, Severity

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedError(RuntimeError):
    """Raised when a PageSpeed Insights call fails."""


def _audit_numeric(audits: dict[str, Any], key: str) -> float | None:
    block = audits.get(key) or {}
    value = block.get("numericValue")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _audit_display(audits: dict[str, Any], key: str) -> str | None:
    block = audits.get(key) or {}
    display = block.get("displayValue")
    return str(display) if display is not None else None


def _field_metrics(experience: dict[str, Any] | None) -> dict[str, Any] | None:
    if not experience:
        return None
    metrics = experience.get("metrics") or {}
    if not metrics:
        return {
            "overall_category": experience.get("overall_category"),
            "metrics": {},
        }
    parsed: dict[str, Any] = {}
    for name, body in metrics.items():
        if not isinstance(body, dict):
            continue
        parsed[name] = {
            "percentile": body.get("percentile"),
            "category": body.get("category"),
        }
    return {
        "overall_category": experience.get("overall_category"),
        "metrics": parsed,
    }


def parse_pagespeed_response(
    payload: dict[str, Any],
    *,
    strategy: str,
    settings: PageSpeedSettings,
) -> dict[str, Any]:
    """Normalize a PSI v5 payload into lab + field metrics and Issue objects."""
    lighthouse = payload.get("lighthouseResult") or {}
    categories = lighthouse.get("categories") or {}
    audits = lighthouse.get("audits") or {}
    perf = categories.get("performance") or {}
    score_01 = perf.get("score")
    performance_score = (
        int(round(float(score_01) * 100)) if score_01 is not None else None
    )

    lcp_ms = _audit_numeric(audits, "largest-contentful-paint")
    cls = _audit_numeric(audits, "cumulative-layout-shift")
    # Prefer INP; fall back to TBT as a lab proxy when INP is absent.
    inp_ms = _audit_numeric(audits, "interaction-to-next-paint")
    tbt_ms = _audit_numeric(audits, "total-blocking-time")
    fcp_ms = _audit_numeric(audits, "first-contentful-paint")
    speed_index = _audit_numeric(audits, "speed-index")

    lab = {
        "performance_score": performance_score,
        "lcp_ms": round(lcp_ms, 1) if lcp_ms is not None else None,
        "lcp_display": _audit_display(audits, "largest-contentful-paint"),
        "cls": round(cls, 3) if cls is not None else None,
        "cls_display": _audit_display(audits, "cumulative-layout-shift"),
        "inp_ms": round(inp_ms, 1) if inp_ms is not None else None,
        "inp_display": _audit_display(audits, "interaction-to-next-paint"),
        "tbt_ms": round(tbt_ms, 1) if tbt_ms is not None else None,
        "fcp_ms": round(fcp_ms, 1) if fcp_ms is not None else None,
        "speed_index_ms": round(speed_index, 1) if speed_index is not None else None,
    }

    final_url = (lighthouse.get("finalUrl") or payload.get("id") or "").strip() or None
    issues = _issues_for_lab(lab, strategy=strategy, url=final_url, settings=settings)

    return {
        "strategy": strategy,
        "url": final_url,
        "lab": lab,
        "field": _field_metrics(payload.get("loadingExperience")),
        "origin_field": _field_metrics(payload.get("originLoadingExperience")),
        "issues": issues,
        "source": "pagespeed_insights",
    }


def _issues_for_lab(
    lab: dict[str, Any],
    *,
    strategy: str,
    url: str | None,
    settings: PageSpeedSettings,
) -> list[Issue]:
    issues: list[Issue] = []
    score = lab.get("performance_score")
    if score is not None and score < settings.performance_score_warn:
        issues.append(
            Issue(
                code="pagespeed_low_performance",
                severity=Severity.WARNING,
                message=(
                    f"PageSpeed {strategy} performance score is {score}/100 "
                    f"(warn below {settings.performance_score_warn})"
                ),
                url=url,
                details={"strategy": strategy, "performance_score": score},
            )
        )

    lcp = lab.get("lcp_ms")
    if lcp is not None and lcp > settings.lcp_good_ms:
        issues.append(
            Issue(
                code="pagespeed_poor_lcp",
                severity=Severity.WARNING,
                message=(
                    f"LCP is {lcp:.0f}ms on {strategy} "
                    f"(good ≤ {settings.lcp_good_ms:.0f}ms)"
                ),
                url=url,
                details={"strategy": strategy, "lcp_ms": lcp},
            )
        )

    cls = lab.get("cls")
    if cls is not None and cls > settings.cls_good:
        issues.append(
            Issue(
                code="pagespeed_poor_cls",
                severity=Severity.WARNING,
                message=(
                    f"CLS is {cls:.3f} on {strategy} "
                    f"(good ≤ {settings.cls_good})"
                ),
                url=url,
                details={"strategy": strategy, "cls": cls},
            )
        )

    inp = lab.get("inp_ms")
    if inp is not None and inp > settings.inp_good_ms:
        issues.append(
            Issue(
                code="pagespeed_poor_inp",
                severity=Severity.WARNING,
                message=(
                    f"INP is {inp:.0f}ms on {strategy} "
                    f"(good ≤ {settings.inp_good_ms:.0f}ms)"
                ),
                url=url,
                details={"strategy": strategy, "inp_ms": inp},
            )
        )
    return issues


class PageSpeedClient:
    def __init__(self, settings: PageSpeedSettings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.enabled and self.settings.api_key)

    def run(
        self,
        url: str,
        *,
        strategy: str = "mobile",
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.api_key:
            raise PageSpeedError(
                "GOOGLE_PAGESPEED_API_KEY is not set. "
                "Create an API key in Google Cloud and enable PageSpeed Insights API."
            )
        params: dict[str, Any] = {
            "url": url,
            "key": self.settings.api_key,
            "strategy": strategy,
            "category": categories or ["performance"],
        }
        try:
            response = requests.get(
                PSI_ENDPOINT,
                params=params,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise PageSpeedError(f"PageSpeed request failed: {exc}") from exc

        if response.status_code >= 400:
            raise PageSpeedError(
                f"PageSpeed failed ({response.status_code}): {response.text[:500]}"
            )
        payload = response.json() or {}
        return parse_pagespeed_response(
            payload, strategy=strategy, settings=self.settings
        )

    def analyze_url(self, url: str) -> dict[str, Any]:
        """Run configured strategies and merge issues."""
        strategy = (self.settings.strategy or "mobile").lower().strip()
        if strategy == "both":
            strategies = ["mobile", "desktop"]
        elif strategy in {"mobile", "desktop"}:
            strategies = [strategy]
        else:
            strategies = ["mobile"]

        results: list[dict[str, Any]] = []
        issues: list[Issue] = []
        errors: list[str] = []
        for name in strategies:
            try:
                result = self.run(url, strategy=name)
                results.append(result)
                issues.extend(result.get("issues") or [])
            except PageSpeedError as exc:
                errors.append(f"{name}: {exc}")

        if not results and errors:
            return {
                "status": "error",
                "url": url,
                "message": "; ".join(errors),
                "strategies": [],
                "issues": [],
            }

        return {
            "status": "ok" if not errors else "partial",
            "url": url,
            "strategies": results,
            "issues": [i.model_dump(mode="json") for i in issues],
            "issue_objects": issues,
            "errors": errors,
            "source": "pagespeed_insights",
        }
