"""Hermes tool handlers → SEO-Agent tools (no hermes-agent source edits)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

def _find_seo_root() -> Path:
    """Walk up from this file until we find the SEO-Agent project root."""
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        marker = candidate / "pyproject.toml"
        if marker.exists() and "seo-agent" in marker.read_text(encoding="utf-8"):
            return candidate
    # Fallback: integrations/hermes/seo_agent_plugin → repo root is parents[3]
    return here.parents[3]


_SEO_ROOT = _find_seo_root()


def _ensure_seo_path() -> None:
    root = str(_SEO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _parse_keywords(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return None
    return [part.strip() for part in text.split(",") if part.strip()]


def _ok(data: Any) -> str:
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    return json.dumps(payload, default=str)


def _err(message: str) -> str:
    return json.dumps({"error": str(message)})


def _check_seo_available() -> bool:
    try:
        _ensure_seo_path()
        import app  # noqa: F401

        return True
    except Exception:
        return False


def handle_audit_site(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.audit_tool import audit_site

        url = args.get("url")
        if not url:
            return _err("url is required")

        audit = audit_site(
            str(url),
            max_pages=args.get("max_pages"),
            max_depth=args.get("max_depth"),
            save=bool(args.get("save", True)),
            compare=bool(args.get("compare", False)),
            optimize=bool(args.get("optimize", False)),
            target_keywords=_parse_keywords(args.get("target_keywords")),
        )
        # Structured SEO metrics first so the LLM/report path has accurate facts
        # before Markdown generation. Full raw HTML is never returned.
        seo_metrics = (audit.summary or {}).get("seo_metrics") or {}
        return _ok(
            {
                "audit_id": audit.audit_id,
                "seed_url": audit.seed_url,
                "score": audit.score,
                "pages": len(audit.pages),
                "issues": len(audit.issues),
                "summary": {
                    "pages": audit.summary.get("pages"),
                    "issues": audit.summary.get("issues"),
                    "severity": audit.summary.get("severity"),
                    "analyzers_run": audit.summary.get("analyzers_run"),
                },
                "seo_metrics": seo_metrics,
                "analyzer_results": [
                    {
                        "analyzer": result.analyzer,
                        "metrics": result.metrics,
                        "issue_count": len(result.issues),
                        "error": result.error,
                    }
                    for result in audit.analyzer_results
                ],
                "top_issues": [
                    {
                        "code": i.code,
                        "severity": i.severity.value,
                        "message": i.message,
                        "url": i.url,
                        "details": i.details,
                    }
                    for i in audit.issues[:40]
                ],
                "diff": audit.diff.model_dump(mode="json") if audit.diff else None,
                "optimization_status": (
                    audit.optimization.status if audit.optimization else None
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_optimize_page(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.optimize_tool import optimize_page

        url = args.get("url")
        if not url:
            return _err("url is required")
        result = optimize_page(
            str(url),
            target_keywords=_parse_keywords(args.get("target_keywords")),
        )
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_generate_report(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.report_tool import generate_report

        url = args.get("url")
        audit_id = args.get("audit_id")
        if not url and not audit_id:
            return _err("url or audit_id is required")

        artifact = generate_report(
            url=str(url) if url else None,
            audit_id=str(audit_id) if audit_id else None,
            format=str(args.get("format") or "markdown"),
            max_pages=args.get("max_pages"),
            save=True,
        )
        content = artifact.content
        # Keep Hermes replies bounded
        if len(content) > 12000:
            content = content[:12000] + "\n\n…[truncated]"
        return _ok(
            {
                "audit_id": artifact.audit_id,
                "format": artifact.format.value,
                "content": content,
                "metadata": artifact.metadata,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_compare_audits(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.compare_tool import compare_audits

        url = args.get("url")
        if not url:
            return _err("url is required")
        diff = compare_audits(str(url), max_pages=args.get("max_pages"), save=True)
        return _ok(diff)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_list_seo_history(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.history_tool import list_history

        url = args.get("url")
        if not url:
            return _err("url is required")
        result = list_history(str(url), limit=int(args.get("limit") or 20))
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
