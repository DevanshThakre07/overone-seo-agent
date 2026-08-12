"""Shared report trust labels — skipped / not-run signals stay visible.

S1 Report trust: Markdown + PDF must not silently omit integrations the
dashboard would show as blank / Not run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Statuses that mean "honest empty" — still show a section stub.
_NOT_RUN = frozenset({"skipped", "blank", ""})
_UNAVAILABLE = frozenset(
    {
        "unavailable",
        "not_connected",
        "no_matching_property",
        "not_provided",
        "caller_provided_not_researched",
    }
)
_ERROR = frozenset({"error"})
_OKISH = frozenset({"ok", "researched", "partial", "provisional"})


@dataclass(frozen=True)
class SignalTrust:
    key: str
    title: str
    status: str
    trust_label: str
    reason: str
    show_data: bool
    block: dict[str, Any]


_DEFAULT_REASONS: dict[str, str] = {
    "pagespeed": (
        "PageSpeed not requested on this audit "
        "(enable pagespeed or set GOOGLE_PAGESPEED_API_KEY)."
    ),
    "google_search_console": (
        "Search Console not requested — Connect Google and pass gsc_account_id."
    ),
    "google_analytics": (
        "GA4 not requested — pass include_ga4=true with a connected Google account."
    ),
    "serp": (
        "SERP/rank not requested — pass include_serp=true with target keywords."
    ),
    "backlinks": (
        "Backlinks not requested — pass include_backlinks=true."
    ),
    "keyword_research": (
        "Keyword research unavailable or not configured (DataForSEO)."
    ),
    "optimize": (
        "Optimize advice not run — pass optimize=true to include AI rewrite suggestions."
    ),
}

_SIGNAL_DEFS: tuple[tuple[str, str], ...] = (
    ("pagespeed", "PageSpeed / Core Web Vitals"),
    ("google_search_console", "Google Search Console"),
    ("google_analytics", "Google Analytics (GA4)"),
    ("serp", "SERP / Rankings"),
    ("backlinks", "Backlinks"),
    ("keyword_research", "Keyword Research"),
)


def trust_label_for_status(status: str | None) -> str:
    s = (status or "").strip().lower()
    if not s or s in _NOT_RUN:
        return "Not run"
    if s in _UNAVAILABLE:
        return "Unavailable"
    if s in _ERROR:
        return "Error"
    if s in _OKISH:
        return "OK"
    return s.replace("_", " ").title()


def _reason_for(key: str, block: dict[str, Any], status: str) -> str:
    msg = (block.get("message") or "").strip()
    if msg:
        return msg
    if status in _NOT_RUN or not status:
        return _DEFAULT_REASONS.get(key, "Not included on this audit.")
    if status in _ERROR:
        return _DEFAULT_REASONS.get(key, f"Status: {status}")
    if status in _UNAVAILABLE:
        return _DEFAULT_REASONS.get(key, f"Status: {status}")
    # OK / researched / partial — never reuse the "not requested" defaults.
    if key == "google_search_console":
        site = block.get("matched_site_url") or (block.get("snapshot") or {}).get(
            "site_url"
        )
        return (
            f"Search Console included (property {site})."
            if site
            else "Search Console included on this audit."
        )
    if key == "google_analytics":
        pid = block.get("property_id") or (block.get("snapshot") or {}).get(
            "property_id"
        )
        return (
            f"GA4 included (property {pid})."
            if pid
            else "GA4 included on this audit."
        )
    if key == "pagespeed":
        return "PageSpeed / CWV included on this audit."
    if key == "serp":
        return "SERP / rank included on this audit."
    if key == "backlinks":
        return "Backlinks included on this audit."
    if key == "keyword_research":
        return "Keyword research included on this audit."
    return f"Status: {status}"


def describe_summary_signal(
    summary: dict[str, Any],
    key: str,
    *,
    title: str | None = None,
) -> SignalTrust:
    raw = summary.get(key)
    block = dict(raw) if isinstance(raw, dict) else {}
    status = str(block.get("status") or "").strip().lower()
    label = trust_label_for_status(status or None)
    show_data = False
    if label == "OK" or status in {"researched", "partial", "provisional"}:
        show_data = bool(block)
    if key == "keyword_research" and status in _UNAVAILABLE:
        show_data = False
    return SignalTrust(
        key=key,
        title=title or key,
        status=status or "skipped",
        trust_label=label,
        reason=_reason_for(key, block, status),
        show_data=show_data,
        block=block,
    )


def describe_optimize_signal(
    summary: dict[str, Any],
    *,
    has_optimization: bool,
    optimization_status: str | None = None,
    optimization_message: str | None = None,
) -> SignalTrust:
    if has_optimization:
        status = (optimization_status or "ok").strip().lower()
        label = "OK" if status in {"ok", "partial", ""} else trust_label_for_status(status)
        reason = (
            (optimization_message or "").strip()
            or "Optimize advice included on this audit."
        )
        return SignalTrust(
            key="optimize",
            title="Optimize advice",
            status=status or "ok",
            trust_label=label,
            reason=reason,
            show_data=True,
            block={"status": status, "message": optimization_message},
        )
    opt_status = summary.get("optimization_status")
    if isinstance(opt_status, dict):
        sig = describe_summary_signal(
            {"optimize": opt_status}, "optimize", title="Optimize advice"
        )
        return SignalTrust(
            key=sig.key,
            title="Optimize advice",
            status=sig.status,
            trust_label=sig.trust_label,
            reason=sig.reason,
            show_data=False,
            block=sig.block,
        )
    return SignalTrust(
        key="optimize",
        title="Optimize advice",
        status="skipped",
        trust_label="Not run",
        reason=_DEFAULT_REASONS["optimize"],
        show_data=False,
        block={},
    )


def integration_signal_inventory(summary: dict[str, Any]) -> list[SignalTrust]:
    """Ordered integration rows for MD/PDF trust stubs."""
    return [
        describe_summary_signal(summary, key, title=title)
        for key, title in _SIGNAL_DEFS
    ]


def markdown_trust_lines(sig: SignalTrust) -> list[str]:
    """Common heading + trust bullets for a signal section."""
    return [
        f"## {sig.title}",
        "",
        f"- Trust: **{sig.trust_label}**",
        f"- Status: **{sig.status}**",
        f"- {sig.reason}",
        "",
    ]


def is_provisional_score(summary_or_doc_summary: Any) -> bool:
    """True when score should be labeled provisional / withheld."""
    if summary_or_doc_summary is None:
        return False
    if isinstance(summary_or_doc_summary, dict):
        if summary_or_doc_summary.get("score_note"):
            return True
        if summary_or_doc_summary.get("score_status") == "provisional":
            return True
        rendering = summary_or_doc_summary.get("rendering") or {}
        return bool(rendering.get("rendering_incomplete"))
    if getattr(summary_or_doc_summary, "score_note", None):
        return True
    if getattr(summary_or_doc_summary, "rendering_warning", None):
        return True
    return False
