"""Assemble a full-tool dashboard payload from saved audit + safe config probes.

Never fails the dashboard on paid/API errors — those sections stay blank.
Does not trigger DataForSEO SERP/rank/backlinks/keyword live calls (cost).
"""

from __future__ import annotations

from typing import Any

from app.config.settings import Settings, get_settings
from app.repositories.factory import get_audit_repository, get_schedule_repository
from app.services.memory_service import MemoryService
from app.utils.url import normalize_url


def _blank(reason: str = "") -> dict[str, Any]:
    return {"status": "blank", "available": False, "data": None, "reason": reason}


# Statuses that must never look like a successful filled panel.
_BLANK_STATUSES = frozenset(
    {
        "skipped",
        "unavailable",
        "error",
        "not_connected",
        "no_matching_property",
        "missing_scope",
        "payment_required",
        "fetch_failed",
        "caller_provided_not_researched",
    }
)


def _filled(data: Any, *, status: str = "ok") -> dict[str, Any]:
    if data is None:
        return _blank("No data")
    if isinstance(data, dict) and data.get("status") in _BLANK_STATUSES:
        return {
            "status": "blank",
            "available": False,
            "data": None,
            "reason": data.get("message") or data.get("status") or "Unavailable",
            "raw_status": data.get("status"),
        }
    # Partial SERP/etc. still show data but keep honest status.
    if isinstance(data, dict) and data.get("status") == "partial":
        return {
            "status": "partial",
            "available": True,
            "data": data,
            "reason": data.get("message") or "Partial results",
        }
    return {"status": status, "available": True, "data": data, "reason": ""}


class DashboardService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = get_audit_repository(self.settings)
        self.memory = MemoryService(self.repo)

    def build(
        self,
        url: str,
        *,
        trend_limit: int = 12,
        gsc_account_id: str | None = None,
        ga4_property_id: str | None = None,
    ) -> dict[str, Any]:
        seed = normalize_url(url)
        latest = self.memory.latest(seed)
        trends = self.memory.trends(seed, limit=trend_limit)
        history = self._history_entries(seed, limit=trend_limit)
        config = self._config_status()
        schedules = self._schedules_section(seed)
        gsc_live = self._safe_gsc(gsc_account_id, seed)
        ga4_live = self._safe_ga4(gsc_account_id, ga4_property_id)
        rank_history = self._rank_history_section(seed)

        if latest is None:
            return {
                "status": "empty",
                "url": seed,
                "message": (
                    "No saved audits yet. Run an audit with save=true "
                    "(Dashboard Run audit or POST /audit)."
                ),
                "config": config,
                "tools": self._tools_catalog(
                    config,
                    None,
                    gsc_live,
                    ga4_section=ga4_live,
                    trends=trends,
                    rank_history=rank_history,
                    schedules=schedules,
                ),
                "audit": _blank("No saved audit"),
                "pagespeed": _blank("No saved audit"),
                "google_search_console": gsc_live if gsc_live.get("available") else _blank(
                    "No saved audit — pass gsc_account_id for live status"
                ),
                "google_analytics": ga4_live if ga4_live.get("available") else _blank(
                    "No saved audit — pass gsc_account_id + ga4_property_id, "
                    "or run audit with include_ga4=true"
                ),
                "keywords": _blank("No keyword research on a saved audit"),
                "serp": _blank("No SERP data — opt in with include_serp on audit"),
                "rank": _blank("No rank checks — opt in with include_serp + keywords"),
                "rank_history": rank_history,
                "backlinks": _blank(
                    "No backlinks data — opt in with include_backlinks on audit"
                ),
                "recommendations": _blank("No saved audit"),
                "optimization": _blank("No optimization run"),
                "keyword_plan": _blank("Use keyword_plan tool on a URL"),
                "login_wall": _blank("Use check_login_wall or auth crawl on audit"),
                "crawl_auth": _blank("No saved audit"),
                "rendering": _blank("No saved audit"),
                "analyzers": _blank("No saved audit"),
                "top_issues": _blank("No saved audit"),
                "trends": _filled(trends) if trends.get("count") else _blank(
                    trends.get("message") or "No trend points"
                ),
                "history": _filled(history) if history else _blank("No history"),
                "schedules": schedules,
                "share": _blank("Save an audit first, then POST /report/{id}/share"),
                "compare": _blank("Need 2+ saved audits to compare"),
            }

        summary = latest.summary or {}
        pagespeed = summary.get("pagespeed")
        gsc_saved = summary.get("google_search_console")
        ga4_saved = summary.get("google_analytics")
        serp = summary.get("serp")
        backlinks = summary.get("backlinks")
        keywords = summary.get("keyword_research")
        # rank_history already computed before the empty early-return
        recs = summary.get("recommendations") or []
        optimization = None
        if latest.optimization is not None:
            opt = latest.optimization
            advice_pages = []
            for p in (opt.pages or [])[:5]:
                advice_pages.append(
                    {
                        "url": p.url,
                        "improved_title": p.improved_title,
                        "improved_meta_description": p.improved_meta_description,
                        "improved_h1": p.improved_h1,
                        "heading_suggestions": (p.heading_suggestions or [])[:6],
                        "keyword_suggestions": (p.keyword_suggestions or [])[:8],
                        "faq_suggestions": [
                            {
                                "question": getattr(f, "question", None)
                                if not isinstance(f, dict)
                                else f.get("question"),
                                "answer": getattr(f, "answer", None)
                                if not isinstance(f, dict)
                                else f.get("answer"),
                            }
                            for f in (p.faq_suggestions or [])[:3]
                        ],
                        "notes": (p.notes or [])[:6],
                    }
                )
            optimization = {
                "status": opt.status,
                "message": opt.message or "",
                "target_keywords": list(opt.target_keywords or []),
                "page_count": len(opt.pages or []),
                "pages": advice_pages,
                "source": "saved_audit",
            }
        elif summary.get("optimization_status"):
            optimization = {
                "status": summary.get("optimization_status"),
                "page_count": 0,
                "pages": [],
                "source": "audit_summary",
            }

        rank_checks = []
        if isinstance(serp, dict) and serp.get("checks"):
            for check in serp.get("checks") or []:
                rank_checks.append(
                    {
                        "keyword": check.get("keyword"),
                        "rank": check.get("rank"),
                        "status": check.get("status"),
                        "message": check.get("message"),
                    }
                )

        opportunities = self._opportunities(recs, gsc_saved if isinstance(gsc_saved, dict) else {})
        top_issues = [
            {
                "code": i.code,
                "severity": i.severity.value,
                "message": i.message,
                "url": i.url,
            }
            for i in sorted(
                latest.issues,
                key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(
                    x.severity.value, 3
                ),
            )[:25]
        ]

        # Prefer live GSC (match + fresh performance). Fall back to saved
        # snapshot only when live fetch has no snapshot yet.
        gsc_section = gsc_live if gsc_live.get("available") else _filled(gsc_saved)
        live_data = (gsc_live.get("data") or {}) if gsc_live.get("available") else {}
        live_snap = live_data.get("snapshot") if isinstance(live_data, dict) else None
        saved_ok = isinstance(gsc_saved, dict) and gsc_saved.get("status") == "ok"
        if gsc_live.get("available") and live_data.get("matches_audit_url"):
            if live_snap:
                gsc_section = _filled({**live_data, "status": "ok"})
            elif saved_ok:
                gsc_section = _filled(
                    {
                        **live_data,
                        "snapshot": gsc_saved.get("snapshot") or gsc_saved,
                        "snapshot_source": "saved_audit",
                        "status": "ok",
                        "matched_site_url": gsc_saved.get("matched_site_url")
                        or live_data.get("matched_site_url"),
                    }
                )

        # Prefer live GA4 when available (fresh + preferred property).
        ga4_section = ga4_live if ga4_live.get("available") else _filled(ga4_saved)

        audit_block = {
            "audit_id": latest.audit_id,
            "created_at": latest.created_at.isoformat(),
            "score": latest.score,
            "score_status": summary.get("score_status"),
            "score_note": summary.get("score_note"),
            "pages": len(latest.pages),
            "issues": len(latest.issues),
            "severity": summary.get("severity") or {},
            "seed_url": latest.seed_url,
        }

        payload = {
            "status": "ok",
            "url": seed,
            "message": "",
            "config": config,
            "tools": [],  # filled after sections so has_data is honest
            "audit": _filled(audit_block),
            "pagespeed": _filled(pagespeed),
            "google_search_console": gsc_section,
            "google_analytics": ga4_section,
            "keywords": _filled(keywords),
            "serp": _filled(serp),
            "rank": _filled(rank_checks) if rank_checks else _blank(
                "No rank rows — run audit with include_serp + target_keywords"
            ),
            "rank_history": rank_history,
            "backlinks": _filled(backlinks),
            "recommendations": _filled(
                {
                    "count": len(recs),
                    "pages": [
                        {
                            "url": r.get("url"),
                            "actions": [
                                {
                                    "code": a.get("code"),
                                    "message": a.get("message"),
                                    "evidence": a.get("evidence"),
                                    "current_value": a.get("current_value"),
                                    "suggested_value": a.get("suggested_value"),
                                }
                                for a in (r.get("actions") or [])[:8]
                            ],
                        }
                        for r in recs[:10]
                    ],
                    "opportunities": opportunities[:20],
                }
            )
            if recs or opportunities
            else _blank("No recommendations on latest audit"),
            "optimization": _filled(optimization)
            if optimization
            else _blank("No optimize run on this audit"),
            "keyword_plan": _blank(
                "Click Get keyword placement on the dashboard (POST /keyword-plan)"
            ),
            "login_wall": _filled((summary.get("crawl_auth") or {}).get("login_wall"))
            if (summary.get("crawl_auth") or {}).get("login_wall")
            else _blank("No login-wall probe stored"),
            "crawl_auth": _filled(summary.get("crawl_auth")),
            "rendering": _filled(summary.get("rendering")),
            "analyzers": _filled(
                {
                    "run": summary.get("analyzers_run") or [],
                    "results": [
                        {
                            "analyzer": r.analyzer,
                            "issue_count": len(r.issues),
                            "error": r.error,
                            "metrics": {
                                k: v
                                for k, v in (r.metrics or {}).items()
                                if not isinstance(v, (dict, list))
                            }
                            if r.metrics
                            else {},
                            "issues": [
                                {
                                    "code": i.code,
                                    "severity": getattr(i.severity, "value", i.severity),
                                    "message": i.message,
                                    "url": i.url,
                                }
                                for i in (r.issues or [])[:12]
                            ],
                        }
                        for r in (latest.analyzer_results or [])
                    ],
                }
            )
            if (latest.analyzer_results or summary.get("analyzers_run"))
            else _blank("No analyzer results on latest audit"),
            "top_issues": _filled(top_issues) if top_issues else _blank("No issues"),
            "trends": _filled(trends) if trends.get("count") else _blank(
                trends.get("message") or "Need more saved audits"
            ),
            "history": _filled(history) if history else _blank("No history"),
            "schedules": schedules,
            "share": _filled(
                {
                    "audit_id": latest.audit_id,
                    "create": f"POST /report/{latest.audit_id}/share",
                    "pdf": f"/report/{latest.audit_id}?format=pdf",
                    "hint": (
                        "Create a public share link, then open "
                        "/share/{token}?format=pdf — or download PDF via "
                        f"/report/{latest.audit_id}?format=pdf"
                    ),
                }
            ),
            "compare": self._compare_section(latest, history),
            # Back-compat for older UI
            "latest": audit_block,
            "opportunities": opportunities[:20],
        }
        payload["tools"] = self._tools_catalog(
            config,
            summary,
            gsc_section,
            ga4_section=ga4_section,
            trends=trends,
            rank_history=payload["rank_history"],
            schedules=schedules,
        )
        return payload

    def _compare_section(
        self, latest: Any, history: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if len(history) < 2:
            return _blank("Need 2+ saved audits to compare score and issues")
        try:
            diff = self.memory.compare(latest)
        except Exception as exc:  # noqa: BLE001
            return _blank(f"Compare unavailable: {exc}")
        if not diff.has_baseline:
            return _blank(diff.summary or "No previous audit found for this URL")
        return _filled(
            {
                "ready": True,
                "history_count": len(history),
                "score_delta": diff.score_delta,
                "current_score": diff.current_score,
                "previous_score": diff.previous_score,
                "current_audit_id": diff.current_audit_id,
                "previous_audit_id": diff.previous_audit_id,
                "new_issues": len(diff.new_issues),
                "resolved_issues": len(diff.resolved_issues),
                "unchanged_issue_count": diff.unchanged_issue_count,
                "summary": diff.summary,
                "hint": "Latest saved audit vs the previous one for this URL.",
            }
        )

    def _rank_history_section(self, seed: str) -> dict[str, Any]:
        try:
            from app.repositories.factory import get_rank_history_repository
            from app.services.rank_history_service import RankHistoryService

            data = RankHistoryService(
                get_rank_history_repository(self.settings)
            ).history(url=seed, limit=40)
            if data.get("count"):
                return _filled(
                    {
                        "count": data.get("count"),
                        "target_domain": data.get("target_domain"),
                        "series": data.get("series") or {},
                        "points": (data.get("points") or [])[:20],
                        "message": data.get("message") or "",
                    }
                )
            return _blank(data.get("message") or "No rank history yet")
        except Exception as exc:  # noqa: BLE001
            return _blank(f"Rank history unavailable: {exc}")

    def _config_status(self) -> dict[str, Any]:
        pagespeed_ok = False
        dataforseo_ok = False
        gsc_oauth_ok = False
        try:
            from app.integrations.google.pagespeed_service import PageSpeedService

            pagespeed_ok = PageSpeedService(self.settings).is_configured()
        except Exception:  # noqa: BLE001
            pagespeed_ok = False
        try:
            from app.integrations.dataforseo.competitive import CompetitiveSeoService

            dataforseo_ok = CompetitiveSeoService(self.settings).is_configured()
        except Exception:  # noqa: BLE001
            dataforseo_ok = False
        try:
            from app.integrations.google.service import GoogleSearchConsoleService

            gsc_oauth_ok = GoogleSearchConsoleService(self.settings).is_configured()
        except Exception:  # noqa: BLE001
            gsc_oauth_ok = False
        return {
            "pagespeed_configured": pagespeed_ok,
            "dataforseo_configured": dataforseo_ok,
            "gsc_oauth_configured": gsc_oauth_ok,
            "openai_configured": bool(self.settings.openai_api_key),
            "alerts_configured": bool(
                (self.settings.alerts.webhook_url or "").strip()
            ),
            "alert_score_drop_threshold": self.settings.alerts.score_drop_threshold,
        }

    def _safe_gsc(
        self, account_id: str | None, seed_url: str | None = None
    ) -> dict[str, Any]:
        if not account_id:
            return _blank("Pass gsc_account_id for live GSC status")
        try:
            from app.integrations.google.service import (
                GoogleSearchConsoleService,
                _match_site,
            )

            svc = GoogleSearchConsoleService(self.settings)
            status = svc.status(account_id)
            if not status.get("connected"):
                return _blank(status.get("message") or "GSC not connected")
            sites_payload = svc.list_sites(account_id)
            sites = sites_payload.get("sites") or []
            matched = _match_site(seed_url or "", sites) if seed_url else None
            site_urls = [s.get("site_url") for s in sites if s.get("site_url")]
            if seed_url and not matched:
                message = (
                    "Google is connected, but none of these Search Console "
                    f"properties match {seed_url}. Verify this site in Search "
                    "Console (or audit a URL that matches a listed property)."
                )
            elif matched:
                message = f"Matched property for this URL: {matched}"
            else:
                message = None
            payload: dict[str, Any] = {
                "account_id": account_id,
                "email": status.get("email"),
                "connected": True,
                "sites": sites,
                "site_count": sites_payload.get("count") or len(sites),
                "seed_url": seed_url,
                "matched_site_url": matched,
                "matches_audit_url": bool(matched),
                "available_sites": site_urls,
                "message": message,
                "snapshot_source": None,
            }
            # Live performance (same idea as GA4) — don't leave the panel on a
            # stale empty snapshot from an older saved audit.
            if matched:
                try:
                    snap = svc.performance(account_id, matched, days=28, top_n=20)
                    payload["snapshot"] = snap
                    payload["snapshot_source"] = "live"
                    payload["status"] = "ok"
                    n_q = len((snap or {}).get("top_queries") or [])
                    n_opp = int((snap or {}).get("opportunity_count") or 0)
                    if n_q == 0 and n_opp == 0:
                        payload["message"] = (
                            f"{message}. Search Console returned no queries in "
                            "the last 28 days yet (new/low-traffic sites are normal)."
                        )
                    elif n_opp == 0:
                        payload["message"] = (
                            f"{message}. No page-2 opportunities yet "
                            "(need queries with impressions on positions ~11–20)."
                        )
                except Exception as exc:  # noqa: BLE001
                    payload["snapshot_error"] = str(exc)
            return _filled(payload)
        except Exception as exc:  # noqa: BLE001
            return _blank(str(exc))

    def _safe_ga4(
        self,
        account_id: str | None,
        property_id: str | None,
    ) -> dict[str, Any]:
        if not account_id:
            return _blank("Pass gsc_account_id for live GA4")
        try:
            from app.integrations.google.ga4_service import Ga4Service

            ga4 = Ga4Service(self.settings)
            status = ga4.status(account_id)
            if not status.get("ga4_ready"):
                return _blank(
                    status.get("message")
                    or "GA4 not ready — reconnect Google for Analytics scope"
                )
            resolved = ga4.resolve_property_id(account_id, property_id)
            props = ga4.list_properties(account_id)
            properties = props.get("properties") or []
            preferred = props.get("preferred_ga4_property_id")
            if resolved:
                report = ga4.report(account_id, resolved, days=28, top_n=10)
                return _filled(
                    {
                        "account_id": account_id,
                        "property_id": resolved,
                        "used_saved_preference": not bool(
                            (property_id or "").strip()
                        ),
                        "preferred_ga4_property_id": preferred,
                        "properties": properties,
                        "email": status.get("email"),
                        "snapshot": report,
                        "has_data": bool(report.get("has_data")),
                    }
                )
            return _filled(
                {
                    "account_id": account_id,
                    "email": status.get("email"),
                    "ga4_ready": True,
                    "properties": properties,
                    "property_count": props.get("count") or 0,
                    "preferred_ga4_property_id": preferred,
                    "hint": (
                        "Pick a GA4 property in the dropdown and click Save default, "
                        "or pass ga4_property_id"
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            return _blank(str(exc))

    def _schedules_for(self, seed: str) -> list[dict[str, Any]]:
        try:
            rows = get_schedule_repository(self.settings).list_all()
            return [r for r in rows if normalize_url(r.get("seed_url") or "") == seed]
        except Exception:  # noqa: BLE001
            return []

    def _schedules_section(self, seed: str) -> dict[str, Any]:
        from app.services.alert_service import AlertService

        alerts = AlertService(self.settings).status()
        rows = self._schedules_for(seed)
        # Always filled so alert status shows even with zero schedules.
        return _filled({"items": rows, "alerts": alerts, "count": len(rows)})

    def _history_entries(self, seed: str, *, limit: int) -> list[dict[str, Any]]:
        try:
            audits = self.memory.history(seed, limit=limit)
            return [
                {
                    "audit_id": a.audit_id,
                    "created_at": a.created_at.isoformat(),
                    "score": a.score,
                    "issues": len(a.issues),
                    "pages": len(a.pages),
                }
                for a in audits
            ]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _opportunities(recs: list[dict], gsc: dict) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for rec in recs[:15]:
            for action in (rec.get("actions") or [])[:8]:
                out.append(
                    {
                        "url": rec.get("url"),
                        "code": action.get("code"),
                        "message": action.get("message"),
                        "current_value": action.get("current_value"),
                        "suggested_value": action.get("suggested_value"),
                        "evidence": action.get("evidence"),
                    }
                )
        snap = gsc.get("snapshot") or {}
        for opp in (snap.get("opportunities") or [])[:10]:
            out.append(
                {
                    "url": opp.get("page"),
                    "code": f"gsc_{opp.get('kind', 'opportunity')}",
                    "message": (
                        f"{opp.get('query')} — pos {opp.get('position')}, "
                        f"impr {opp.get('impressions')}"
                    ),
                }
            )
        return out

    @staticmethod
    def _tools_catalog(
        config: dict[str, Any],
        summary: dict[str, Any] | None,
        gsc_section: dict[str, Any],
        *,
        ga4_section: dict[str, Any] | None = None,
        trends: dict[str, Any] | None = None,
        rank_history: dict[str, Any] | None = None,
        schedules: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        summary = summary or {}
        ga4_section = ga4_section or {}
        trends = trends or {}
        rank_history = rank_history or {}
        schedules = schedules or {}

        def has_ok(key: str) -> bool:
            block = summary.get(key)
            return isinstance(block, dict) and block.get("status") == "ok"

        schedule_items: list[Any] = []
        sched_data = (
            schedules.get("data")
            if isinstance(schedules, dict) and schedules.get("available")
            else schedules
        )
        if isinstance(sched_data, dict):
            schedule_items = list(sched_data.get("items") or [])
        elif isinstance(sched_data, list):
            schedule_items = sched_data

        rank_hist_count = 0
        if isinstance(rank_history, dict) and rank_history.get("available"):
            rh = rank_history.get("data") or {}
            if isinstance(rh, dict):
                rank_hist_count = int(rh.get("count") or 0)
        elif isinstance(rank_history, dict):
            rank_hist_count = int(rank_history.get("count") or 0)

        trend_count = int(trends.get("count") or 0)

        return [
            {
                "id": "audit_site",
                "label": "Site audit",
                "configured": True,
                "has_data": bool(summary),
            },
            {
                "id": "check_pagespeed",
                "label": "PageSpeed / CWV",
                "configured": config.get("pagespeed_configured"),
                "has_data": has_ok("pagespeed"),
            },
            {
                "id": "gsc",
                "label": "Google Search Console",
                "configured": config.get("gsc_oauth_configured"),
                "has_data": bool(
                    gsc_section.get("available") or has_ok("google_search_console")
                ),
            },
            {
                "id": "ga4",
                "label": "Google Analytics (GA4)",
                "configured": config.get("gsc_oauth_configured"),
                "has_data": bool(
                    ga4_section.get("available") or has_ok("google_analytics")
                ),
            },
            {
                "id": "research_keywords",
                "label": "Keyword research",
                "configured": config.get("dataforseo_configured"),
                "has_data": bool(
                    (summary.get("keyword_research") or {}).get("is_real_research")
                ),
            },
            {
                "id": "check_serp",
                "label": "SERP top results",
                "configured": config.get("dataforseo_configured"),
                "has_data": has_ok("serp"),
            },
            {
                "id": "check_rank",
                "label": "Rank check",
                "configured": config.get("dataforseo_configured"),
                "has_data": has_ok("serp"),
            },
            {
                "id": "list_rank_history",
                "label": "Rank history",
                "configured": True,
                "has_data": rank_hist_count > 0,
            },
            {
                "id": "check_backlinks",
                "label": "Backlinks",
                "configured": config.get("dataforseo_configured"),
                "has_data": has_ok("backlinks"),
            },
            {
                "id": "optimize_page",
                "label": "Optimize (advice)",
                "configured": config.get("openai_configured"),
                "has_data": bool(summary.get("optimization_status")),
            },
            {
                "id": "keyword_plan",
                "label": "Keyword placement",
                "configured": True,
                "has_data": False,
            },
            {
                "id": "list_seo_trends",
                "label": "Trends / history",
                "configured": True,
                "has_data": trend_count > 0,
            },
            {
                "id": "schedules",
                "label": "Scheduled audits",
                "configured": True,
                "has_data": len(schedule_items) > 0,
            },
            {
                "id": "alerts",
                "label": "Schedule alerts",
                "configured": config.get("alerts_configured"),
                "has_data": bool(config.get("alerts_configured")),
            },
            {
                "id": "generate_report",
                "label": "Reports / share",
                "configured": True,
                "has_data": bool(summary),
            },
            {
                "id": "check_login_wall",
                "label": "Login wall / auth crawl",
                "configured": True,
                "has_data": bool(summary.get("crawl_auth")),
            },
        ]
