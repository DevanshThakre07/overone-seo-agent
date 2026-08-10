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


def _parse_auth_headers(raw: Any) -> dict[str, str] | None:
    """Accept a string→string map; ignore non-dicts for Hermes safety."""
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out or None


def _pagespeed_highlight(pagespeed: dict[str, Any]) -> dict[str, Any] | None:
    if not pagespeed or pagespeed.get("status") in (None, "skipped"):
        return None
    out: dict[str, Any] = {"status": pagespeed.get("status")}
    for strat in pagespeed.get("strategies") or []:
        lab = strat.get("lab") or {}
        out[str(strat.get("strategy") or "mobile")] = {
            "performance_score": lab.get("performance_score"),
            "lcp_ms": lab.get("lcp_ms"),
            "cls": lab.get("cls"),
            "inp_ms": lab.get("inp_ms"),
        }
    lab = pagespeed.get("lab") or {}
    if lab and "mobile" not in out and "desktop" not in out:
        out["lab"] = {
            "performance_score": lab.get("performance_score"),
            "lcp_ms": lab.get("lcp_ms"),
            "cls": lab.get("cls"),
        }
    issues = pagespeed.get("issues") or []
    out["issue_codes"] = [
        i.get("code") for i in issues if isinstance(i, dict) and i.get("code")
    ][:8]
    return out


def _gsc_highlight(gsc: dict[str, Any]) -> dict[str, Any] | None:
    if not gsc or gsc.get("status") in (None, "skipped"):
        return None
    snap = gsc.get("snapshot") or {}
    return {
        "status": gsc.get("status"),
        "matched_site_url": gsc.get("matched_site_url"),
        "opportunity_count": snap.get("opportunity_count")
        or len(snap.get("opportunities") or []),
        "top_query": ((snap.get("top_queries") or [{}])[0] or {}).get("query"),
        "message": gsc.get("message"),
    }


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


def _smart_truncate_report(content: str, max_chars: int) -> str:
    """Keep high-value sections when a report must be shortened for chat."""
    keep_headers = (
        "## Summary",
        "## PageSpeed",
        "## Google Search Console",
        "## SERP / Rankings",
        "## Backlinks",
        "## Critical Issues",
        "## Warnings",
        "## Suggestions",
        "## Recommendations",
        "## Overall SEO Score",
        "## Keyword Research",
        "## Data Integrity",
    )
    parts: list[str] = []
    current: list[str] = []
    current_header = ""
    for line in content.splitlines():
        if line.startswith("## "):
            if current:
                parts.append((current_header, "\n".join(current)))
            current_header = line.strip()
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append((current_header, "\n".join(current)))

    preferred = [body for header, body in parts if any(h in header for h in keep_headers)]
    if not preferred:
        return content[:max_chars] + "\n\n…[truncated]"
    assembled = "\n\n".join(preferred)
    if len(assembled) > max_chars:
        assembled = assembled[:max_chars]
    return (
        assembled
        + "\n\n…[truncated for chat — ask generate_report again or use audit_id for full JSON]"
    )


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
            gsc_account_id=args.get("gsc_account_id") or None,
            auth_cookie=args.get("auth_cookie") or None,
            auth_headers=_parse_auth_headers(args.get("auth_headers")),
            use_authenticated_crawl=bool(args.get("use_authenticated_crawl", False)),
            include_serp=bool(args.get("include_serp", False)),
            include_backlinks=bool(args.get("include_backlinks", False)),
            include_ga4=bool(args.get("include_ga4", False)),
            ga4_property_id=args.get("ga4_property_id") or None,
        )
        seo_metrics = (audit.summary or {}).get("seo_metrics") or {}
        score_status = (audit.summary or {}).get("score_status") or "final"
        score_note = (audit.summary or {}).get("score_note")
        severity = (audit.summary or {}).get("severity") or {}
        pagespeed = (audit.summary or {}).get("pagespeed") or {}
        gsc = (audit.summary or {}).get("google_search_console") or {}
        recs = (audit.summary or {}).get("recommendations") or []

        # Prioritize CWV / pagespeed codes so Hermes cannot bury them.
        ordered_issues = sorted(
            audit.issues,
            key=lambda i: (
                0 if (i.code or "").startswith("pagespeed_") else 1,
                {"critical": 0, "warning": 1, "info": 2}.get(i.severity.value, 3),
            ),
        )
        top_issues = [
            {
                "code": i.code,
                "severity": i.severity.value,
                "message": i.message,
                "url": i.url,
            }
            for i in ordered_issues[:40]
        ]
        executive = {
            "score": None if score_status == "provisional" else audit.score,
            "score_status": score_status,
            "score_note": score_note,
            "pages": len(audit.pages),
            "severity": severity,
            "headline_issues": top_issues[:8],
            "pagespeed_highlight": _pagespeed_highlight(pagespeed),
            "gsc_highlight": _gsc_highlight(gsc),
            "instruction": (
                "Lead your reply with score, severity counts, pagespeed_highlight, "
                "then headline_issues (PageSpeed codes are sorted first on purpose)."
            ),
        }
        # Slim recommendations for chat — full detail via generate_report.
        slim_recs = []
        for rec in recs[:8]:
            slim_recs.append(
                {
                    "url": rec.get("url"),
                    "actions": [
                        {"code": a.get("code"), "message": a.get("message")}
                        for a in (rec.get("actions") or [])[:6]
                    ],
                }
            )

        return _ok(
            {
                "audit_id": audit.audit_id,
                "seed_url": audit.seed_url,
                "executive_summary": executive,
                # Withhold confident score when rendering was incomplete.
                "score": executive["score"],
                "score_status": score_status,
                "score_note": score_note,
                "raw_score": (audit.summary or {}).get("raw_score", audit.score),
                "pages": len(audit.pages),
                "issues": len(audit.issues),
                "delivery": "inline_json",
                "scope": (audit.summary or {}).get("scope"),
                "rendering": (audit.summary or {}).get("rendering"),
                "url_integrity": (audit.summary or {}).get("url_integrity"),
                "pagespeed": pagespeed,
                "google_search_console": gsc,
                "serp": (audit.summary or {}).get("serp"),
                "backlinks": (audit.summary or {}).get("backlinks"),
                "crawl_auth": (audit.summary or {}).get("crawl_auth"),
                "recommendations": slim_recs,
                "summary": {
                    "pages": audit.summary.get("pages"),
                    "issues": audit.summary.get("issues"),
                    "severity": severity,
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
                "top_issues": top_issues,
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


def handle_check_login_wall(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.login_wall_tool import check_login_wall

        url = args.get("url")
        if not url:
            return _err("url is required")
        result = check_login_wall(str(url))
        result["delivery"] = "inline_json"
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
            auth_cookie=args.get("auth_cookie") or None,
            auth_headers=_parse_auth_headers(args.get("auth_headers")),
            use_authenticated_crawl=bool(args.get("use_authenticated_crawl", False)),
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

        fmt = str(args.get("format") or "markdown").lower()
        artifact = generate_report(
            url=str(url) if url else None,
            audit_id=str(audit_id) if audit_id else None,
            format=fmt,
            max_pages=args.get("max_pages"),
            save=True,
            out=None,
        )
        if fmt == "pdf":
            return _ok(
                {
                    "audit_id": artifact.audit_id,
                    "format": "pdf",
                    "path": artifact.path,
                    "byte_length": artifact.metadata.get("byte_length"),
                    "delivery": "file_path",
                    "message": (
                        "PDF written to path. Tell the user the file location; "
                        "do not paste base64 into chat. "
                        "Also available via GET /report/{audit_id}?format=pdf "
                        "or a share link ?format=pdf."
                    ),
                    "write_instructions": (
                        "PDF is already on disk at 'path'. Do not rewrite it."
                    ),
                }
            )
        content = _strip_diff_markers(artifact.content)
        # Prefer keeping Score + PageSpeed + GSC + Warnings over a hard mid-cut.
        truncated = False
        max_chars = 48_000
        if len(content) > max_chars:
            truncated = True
            content = _smart_truncate_report(content, max_chars)
        return _ok(
            {
                "audit_id": artifact.audit_id,
                "format": artifact.format.value,
                "content": content,
                "truncated": truncated,
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
                    "truncated": truncated,
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
            auth_cookie=args.get("auth_cookie") or None,
            auth_headers=_parse_auth_headers(args.get("auth_headers")),
            use_authenticated_crawl=bool(args.get("use_authenticated_crawl", False)),
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


def handle_list_seo_trends(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.trends_tool import list_seo_trends

        url = args.get("url")
        if not url:
            return _err("url is required")
        result = list_seo_trends(str(url), limit=int(args.get("limit") or 20))
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_list_rank_history(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.rank_history_tool import list_rank_history

        url = args.get("url")
        target = args.get("target")
        if not url and not target:
            return _err("url or target is required")
        result = list_rank_history(
            str(url) if url else None,
            target=str(target) if target else None,
            keyword=str(args["keyword"]) if args.get("keyword") else None,
            limit=int(args.get("limit") or 50),
        )
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_gsc_status(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.gsc_tool import gsc_status

        account_id = args.get("account_id")
        if not account_id:
            return _err("account_id is required")
        result = gsc_status(str(account_id))
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_gsc_sites(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.gsc_tool import gsc_list_sites

        account_id = args.get("account_id")
        if not account_id:
            return _err("account_id is required")
        result = gsc_list_sites(str(account_id))
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_gsc_performance(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.gsc_tool import gsc_performance

        account_id = args.get("account_id")
        site_url = args.get("site_url")
        if not account_id:
            return _err("account_id is required")
        if not site_url:
            return _err("site_url is required")
        result = gsc_performance(
            str(account_id),
            str(site_url),
            days=int(args.get("days") or 28),
            top_n=int(args.get("top_n") or 20),
        )
        # Cap chat-facing opportunity noise; full list still in result.
        opportunities = result.get("opportunities") or []
        if isinstance(opportunities, list) and len(opportunities) > 20:
            result = {
                **result,
                "opportunities": opportunities[:20],
                "opportunities_truncated": True,
            }
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_ga4_status(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.ga4_tool import ga4_status

        account_id = args.get("account_id")
        if not account_id:
            return _err("account_id is required")
        result = ga4_status(str(account_id))
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_ga4_properties(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.ga4_tool import ga4_list_properties

        account_id = args.get("account_id")
        if not account_id:
            return _err("account_id is required")
        result = ga4_list_properties(str(account_id))
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_ga4_set_preference(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.ga4_tool import ga4_set_preference

        account_id = args.get("account_id")
        if not account_id:
            return _err("account_id is required")
        property_id = args.get("property_id")
        result = ga4_set_preference(
            str(account_id),
            None if property_id in (None, "") else str(property_id),
        )
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_ga4_report(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.ga4_tool import ga4_report

        account_id = args.get("account_id")
        property_id = args.get("property_id")
        if not account_id:
            return _err("account_id is required")
        result = ga4_report(
            str(account_id),
            None if property_id in (None, "") else str(property_id),
            days=int(args.get("days") or 28),
            top_n=int(args.get("top_n") or 20),
        )
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_check_serp(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.serp_tool import check_serp

        keyword = args.get("keyword")
        if not keyword:
            return _err("keyword is required")
        result = check_serp(
            str(keyword),
            depth=int(args.get("depth") or 10),
            location_code=args.get("location_code"),
            language_code=args.get("language_code"),
            device=str(args.get("device") or "desktop"),
        )
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_check_rank(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.serp_tool import check_rank

        keyword = args.get("keyword")
        target = args.get("target")
        if not keyword:
            return _err("keyword is required")
        if not target:
            return _err("target is required")
        result = check_rank(
            str(keyword),
            str(target),
            depth=int(args.get("depth") or 20),
            location_code=args.get("location_code"),
            language_code=args.get("language_code"),
            device=str(args.get("device") or "desktop"),
        )
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def handle_check_backlinks(args: dict, **kwargs: Any) -> str:
    try:
        _ensure_seo_path()
        from app.tools.backlinks_tool import check_backlinks

        target = args.get("target")
        if not target:
            return _err("target is required")
        result = check_backlinks(
            str(target),
            referring_limit=int(args.get("referring_limit") or 10),
        )
        result["delivery"] = "inline_json"
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
