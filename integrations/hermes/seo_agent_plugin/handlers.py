"""Hermes tool handlers → SEO-Agent tools (no hermes-agent source edits)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath
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


# Machine-local paths (incl. file:// URIs) must never reach the caller: they are
# meaningless on any other machine and leak the local user's home directory.
_LOCAL_PATH_RE = re.compile(
    r"(?:file://)?(?:/Users/[^/\s]+|/home/[^/\s]+|/private/var|/var/folders|/tmp)"
    r"(?:/[^\s\"',;)\]}]*)?"
)


def _scrub_local_paths(value: Any) -> Any:
    """Recursively replace absolute local paths with portable basenames."""
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            name = PurePosixPath(match.group(0).replace("file://", "")).name
            return f"[local-file:{name}]" if name else "[local-path-removed]"

        return _LOCAL_PATH_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _scrub_local_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_local_paths(v) for v in value]
    return value


def _strip_diff_markers(text: str) -> str:
    """Remove git-diff artifacts if a diff was captured instead of clean content."""
    lines = text.splitlines()
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return text
    if all(ln.startswith(("+", "-")) for ln in body) or any(
        ln.startswith(("+++ ", "--- ", "@@ ")) for ln in body[:5]
    ):
        cleaned = []
        for ln in lines:
            if ln.startswith(("+++ ", "--- ")) or ln.startswith("@@"):
                continue
            cleaned.append(ln[1:] if ln[:1] in {"+", "-", " "} else ln)
        return "\n".join(cleaned)
    return text


def _ok(data: Any) -> str:
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    payload = _scrub_local_paths(payload)
    if isinstance(payload, dict):
        for key in ("path", "file_path", "output_path", "saved_to"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith("/"):
                payload[key] = Path(value).name
        meta = payload.get("metadata")
        if isinstance(meta, dict):
            for key in ("path", "file_path", "output_path", "saved_to"):
                value = meta.get(key)
                if isinstance(value, str) and value.startswith("/"):
                    meta[key] = Path(value).name
    return json.dumps(payload, default=str)


def _err(message: str) -> str:
    return json.dumps({"error": str(message)})


def _arm_write_firewall(url: str) -> None:
    """Lock writes for an external target before any result reaches the model.

    Armed on every URL-scoped SEO call so the host agent physically cannot
    "apply" the returned copy to a local file that was never mapped to it.
    """
    try:
        _ensure_seo_path()
        from app.utils.write_firewall import arm_external_scope

        arm_external_scope(url)
    except Exception:  # noqa: BLE001 - never let the guard break the tool
        pass


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
        _arm_write_firewall(str(url))

        pagespeed_arg = args.get("pagespeed")
        if pagespeed_arg is None:
            pagespeed_opt = None
        else:
            pagespeed_opt = bool(pagespeed_arg)

        audit = audit_site(
            str(url),
            max_pages=args.get("max_pages"),
            max_depth=args.get("max_depth"),
            save=bool(args.get("save", True)),
            compare=bool(args.get("compare", False)),
            optimize=bool(args.get("optimize", False)),
            target_keywords=_parse_keywords(args.get("target_keywords")),
            pagespeed=pagespeed_opt,
        )
        seo_metrics = (audit.summary or {}).get("seo_metrics") or {}
        score_status = (audit.summary or {}).get("score_status") or "final"
        score_note = (audit.summary or {}).get("score_note")
        return _ok(
            {
                "audit_id": audit.audit_id,
                "seed_url": audit.seed_url,
                # Withhold confident score when rendering was incomplete.
                "score": None if score_status == "provisional" else audit.score,
                "score_status": score_status,
                "score_note": score_note,
                "raw_score": (audit.summary or {}).get("raw_score", audit.score),
                "score_breakdown": (audit.summary or {}).get("score_breakdown"),
                "pages": len(audit.pages),
                "issues": len(audit.issues),
                "delivery": "inline_json",
                "scope": (audit.summary or {}).get("scope"),
                "rendering": (audit.summary or {}).get("rendering"),
                "url_integrity": (audit.summary or {}).get("url_integrity"),
                "pagespeed": (audit.summary or {}).get("pagespeed"),
                "recommendations": (audit.summary or {}).get("recommendations") or [],
                "summary": {
                    "pages": audit.summary.get("pages"),
                    "issues": audit.summary.get("issues"),
                    "severity": audit.summary.get("severity"),
                    "analyzers_run": audit.summary.get("analyzers_run"),
                    "score_status": score_status,
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
                "keyword_research": (
                    audit.optimization.keyword_research
                    if audit.optimization
                    else (audit.summary or {}).get("keyword_research")
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_check_pagespeed(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.pagespeed_tool import check_pagespeed

        url = args.get("url")
        if not url:
            return _err("url is required")
        _arm_write_firewall(str(url))

        result = check_pagespeed(str(url), strategy=args.get("strategy"))
        # Compact chat-friendly highlight on top of the full payload.
        highlights: list[dict[str, Any]] = []
        for block in result.get("strategies") or []:
            lab = block.get("lab") or {}
            field = block.get("field") or {}
            highlights.append(
                {
                    "strategy": block.get("strategy"),
                    "performance_score": lab.get("performance_score"),
                    "lcp_ms": lab.get("lcp_ms"),
                    "cls": lab.get("cls"),
                    "inp_ms": lab.get("inp_ms"),
                    "field_overall": field.get("overall_category"),
                }
            )
        return _ok(
            {
                **result,
                "highlights": highlights,
                "note": (
                    "Lab metrics are a single Lighthouse run; prefer field/CrUX "
                    "when present for real-user experience."
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_research_keywords(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.keyword_research_tool import research_keywords_tool

        raw = args.get("keywords")
        if not raw:
            return _err("keywords is required")
        result = research_keywords_tool(
            str(raw),
            location_code=args.get("location_code"),
            language_code=args.get("language_code"),
            include_difficulty=bool(args.get("include_difficulty", True)),
            include_related=args.get("include_related"),
        )
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_optimize_page(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.optimize_tool import optimize_page

        url = args.get("url")
        if not url:
            return _err("url is required")
        _arm_write_firewall(str(url))
        result = optimize_page(
            str(url),
            target_keywords=_parse_keywords(args.get("target_keywords")),
        )
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        if isinstance(payload, dict):
            payload["delivery"] = "inline_json"
            # Explicitly tell callers not to treat brand guesses as research.
            if not payload.get("keyword_research"):
                from app.optimizer.keyword_research import normalize_caller_keywords

                payload["keyword_research"] = normalize_caller_keywords(
                    _parse_keywords(args.get("target_keywords"))
                )
        return _ok(payload)
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

        # Always return content inline for Hermes — do not write machine-local files.
        artifact = generate_report(
            url=str(url) if url else None,
            audit_id=str(audit_id) if audit_id else None,
            format=str(args.get("format") or "markdown"),
            max_pages=args.get("max_pages"),
            save=True,
            out=None,
        )
        content = _strip_diff_markers(artifact.content)
        if len(content) > 12000:
            content = content[:12000] + "\n\n…[truncated]"
        return _ok(
            {
                "audit_id": artifact.audit_id,
                "format": artifact.format.value,
                "content": content,
                "delivery": "inline_content",
                "content_encoding": "plain_markdown",
                "write_instructions": (
                    "This 'content' field is already complete, clean markdown. Write it "
                    "verbatim with a plain file-write. Do NOT use a patch/diff tool, do "
                    "NOT prefix lines with '+' or '-', and do NOT rewrite it yourself."
                ),
                "path": None,
                "metadata": {
                    **(artifact.metadata or {}),
                    "delivery": "inline_content",
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_keyword_plan(args: dict, **kwargs: Any) -> str:
    """Keyword placement plan derived from a LIVE fetch of the URL."""
    try:
        _ensure_seo_path()
        from app.tools.keyword_plan_tool import keyword_plan

        url = args.get("url")
        if not url:
            return _err("url is required")
        _arm_write_firewall(str(url))
        result = keyword_plan(
            str(url),
            target_keywords=_parse_keywords(args.get("target_keywords")),
        )
        result["delivery"] = "inline_json"
        return _ok(result)
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
        payload = diff.model_dump(mode="json") if hasattr(diff, "model_dump") else diff
        if isinstance(payload, dict):
            payload["delivery"] = "inline_json"
        return _ok(payload)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_confirm_site_sources(args: dict, **kwargs: Any) -> str:
    """Map a site to the local files that are genuinely its source.

    The ONLY way to lift the write firewall. Requires explicit paths from the
    user — a bare "yes, go ahead" is not a mapping and will not unlock a write.
    """
    try:
        _ensure_seo_path()
        from app.utils.write_firewall import confirm_site_sources

        url = args.get("url")
        if not url:
            return _err("url is required")

        raw = args.get("paths")
        paths = raw if isinstance(raw, list) else _parse_keywords(raw) or []
        if not paths:
            return _err(
                "paths is required: list the exact local files that contain this "
                "site's source. Do not guess from filenames such as index.html — "
                "ask the user."
            )

        result = confirm_site_sources(str(url), [str(p) for p in paths])
        if result["refused_paths"]:
            result["warning"] = (
                "Refused path(s) inside an agent/tool codebase. That refusal is "
                "not overridable, including by user confirmation."
            )
        return _ok(result)
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
        if isinstance(result, dict):
            result = {**result, "delivery": "inline_json"}
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
