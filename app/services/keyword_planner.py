"""Keyword integration planning grounded in the LIVE page.

This service exists because delegated/generic assistants were answering
"where do these keywords fit on this site?" by grepping the local workspace
instead of fetching the URL. Everything here is derived from a real fetch of
the requested URL, and if that fetch fails the result says so explicitly
instead of degrading into generic advice.
"""

from __future__ import annotations

import re
from typing import Any

from app.config.settings import Settings, get_settings
from app.crawler.auth import auth_policy_block, build_crawl_auth
from app.extractor.html_extractor import HtmlExtractor
from app.logging import get_logger, log_event
from app.models.page import PageExtraction
from app.optimizer.keyword_research import normalize_caller_keywords
from app.services.crawler_service import CrawlerService
from app.utils.integrity import check_url_integrity
from app.utils.scope_guard import build_write_policy

logger = get_logger(__name__)

TITLE_MAX = 60
META_MAX = 155


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _contains(haystack: str | None, needle: str) -> bool:
    h, n = _norm(haystack), _norm(needle)
    return bool(n) and n in h


def humanize_fetch_error(message: str | None) -> str:
    """Turn urllib/Playwright stack noise into something a user can act on."""
    raw = str(message or "unknown error")
    low = raw.lower()
    if any(s in low for s in ("nameresolution", "name or service not known", "getaddrinfo")):
        return "the domain could not be resolved — check the URL spelling"
    if "timed out" in low or "timeout" in low:
        return "the request timed out — the site may be slow or blocking automated access"
    if "ssl" in low or "certificate" in low:
        return "the site's TLS certificate could not be verified"
    if "connection refused" in low:
        return "the server refused the connection"
    if "max retries exceeded" in low:
        return "the site did not respond"
    if "403" in raw or "forbidden" in low:
        return "the site returned 403 Forbidden — it is likely blocking automated requests"
    if "404" in raw:
        return "the page returned 404 Not Found"
    return raw if len(raw) <= 160 else raw[:157] + "…"


class KeywordPlanner:
    def __init__(
        self,
        settings: Settings | None = None,
        crawler_service: CrawlerService | None = None,
        extractor: HtmlExtractor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.crawler_service = crawler_service or CrawlerService(self.settings)
        self.extractor = extractor or HtmlExtractor()

    def plan(
        self,
        url: str,
        *,
        target_keywords: list[str] | None = None,
        auth_cookie: str | None = None,
        auth_headers: dict[str, str] | None = None,
        use_authenticated_crawl: bool = False,
    ) -> dict[str, Any]:
        log_event(logger, "keyword_plan_started", url=url)
        keyword_meta = normalize_caller_keywords(target_keywords)
        keywords = keyword_meta["keywords"]
        crawl_auth = build_crawl_auth(
            auth_cookie=auth_cookie,
            auth_headers=auth_headers,
        )
        use_auth = bool(use_authenticated_crawl) and bool(crawl_auth)
        login_wall = self.crawler_service.probe_login_wall(url)
        auth_meta = auth_policy_block(
            auth=crawl_auth,
            use_authenticated_crawl=use_authenticated_crawl,
            login_wall=login_wall,
            credentials_used=use_auth,
        )

        page, fetch = self.fetch_live_page(
            url,
            auth=crawl_auth if use_auth else None,
        )
        if page is None or page.is_broken:
            reason = humanize_fetch_error(
                fetch.get("error") or (page.error if page else None)
            )
            return {
                "status": "fetch_failed",
                "requested_url": url,
                "live_fetch": fetch,
                "analysis_is_site_specific": False,
                "disclaimer": (
                    f"Could not fetch {url} ({reason}) — this analysis is generic, "
                    "NOT site-specific. No claims below are based on the actual page. "
                    "Do not present generic advice as tailored to this site."
                ),
                "target_keywords": keywords,
                "keyword_research": keyword_meta,
                "placements": [],
                "findings": [],
                "write_policy": build_write_policy(url),
                "crawl_auth": auth_meta,
            }

        integrity = check_url_integrity(
            url, [page.final_url], redirect_chains=[page.redirect_chain]
        )

        findings, placements = analyze_keyword_placement(page, keywords)

        return {
            "status": "ok",
            "requested_url": url,
            "analyzed_url": page.final_url,
            "live_fetch": fetch,
            "analysis_is_site_specific": True,
            "url_integrity": integrity,
            "page_evidence": {
                "title": page.title,
                "meta_description": page.meta_description,
                "h1": page.h1,
                "h2": page.h2[:10],
                "h3": page.h3[:10],
                "word_count": page.word_count,
                "js_rendered": page.js_rendered,
                "internal_links": len(page.internal_links),
                "text_excerpt": (page.text_sample or "")[:400],
            },
            "target_keywords": keywords,
            "keyword_research": keyword_meta,
            "findings": findings,
            "placements": placements,
            "write_policy": build_write_policy(url),
            "notes": [keyword_meta["message"]],
            "crawl_auth": auth_meta,
        }

    def fetch_live_page(
        self,
        url: str,
        *,
        auth=None,
    ) -> tuple[PageExtraction | None, dict[str, Any]]:
        """Fetch + render the URL. Returns (page, fetch_diagnostics)."""
        crawl = self.settings.crawl
        original = (crawl.max_pages, crawl.max_depth, crawl.check_external_links)
        crawl.max_pages, crawl.max_depth, crawl.check_external_links = 1, 0, False
        try:
            results, stats = self.crawler_service.crawl(url, auth=auth)
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "keyword_plan_fetch_failed", url=url, error=str(exc))
            return None, {"ok": False, "url": url, "error": str(exc), "method": "http"}
        finally:
            crawl.max_pages, crawl.max_depth, crawl.check_external_links = original

        pages = self.extractor.extract_many(results, stats.seed_url)
        if not pages:
            return None, {
                "ok": False,
                "url": url,
                "error": "no page content extracted",
                "method": "http",
            }

        page = pages[0]
        diag = (page.seo_signals or {}).get("render_diagnostics") or {}
        fetch = {
            "ok": not page.is_broken,
            "url": url,
            "final_url": page.final_url,
            "status_code": page.status_code,
            "js_rendered": page.js_rendered,
            "method": "playwright" if page.js_rendered else "http",
            "word_count": page.word_count,
            "render_diagnostics": diag,
            "error": page.error,
        }
        return page, fetch


def analyze_keyword_placement(
    page: PageExtraction, keywords: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Report which slots on the REAL page already contain each keyword."""
    title = page.title or ""
    meta = page.meta_description or ""
    h1 = page.h1[0] if page.h1 else ""
    body = page.text_sample or ""

    findings: list[dict[str, Any]] = []
    placements: list[dict[str, Any]] = []

    if not keywords:
        findings.append(
            {
                "keyword": None,
                "severity": "info",
                "finding": (
                    "No target keywords were provided, so keyword placement could not "
                    "be checked against this page."
                ),
            }
        )
        return findings, placements

    for kw in keywords:
        present = {
            "title": _contains(title, kw),
            "meta_description": _contains(meta, kw),
            "h1": _contains(h1, kw),
            "h2": any(_contains(h, kw) for h in page.h2),
            "body": _contains(body, kw),
        }
        missing = [slot for slot, hit in present.items() if not hit]
        occurrences = len(re.findall(re.escape(_norm(kw)), _norm(body))) if kw else 0

        for slot, hit in present.items():
            label = slot.replace("_", " ")
            if hit:
                findings.append(
                    {
                        "keyword": kw,
                        "severity": "ok",
                        "finding": f'"{kw}" already appears in the {label}.',
                    }
                )
                continue
            current = {
                "title": title,
                "meta_description": meta,
                "h1": h1,
                "h2": "; ".join(page.h2[:3]),
                "body": f"{page.word_count} words of body copy",
            }[slot]
            findings.append(
                {
                    "keyword": kw,
                    "severity": "critical" if slot in {"title", "h1"} else "warning",
                    "finding": (
                        f'Your {label} does not include "{kw}". '
                        f"Current {label}: {current or '(empty)'}"
                    ),
                }
            )

        placements.append(
            {
                "keyword": kw,
                "present_in": [s for s, hit in present.items() if hit],
                "missing_from": missing,
                "body_occurrences": occurrences,
                "rewrites": build_keyword_rewrites(page, kw, present),
            }
        )

    return findings, placements


def build_keyword_rewrites(
    page: PageExtraction, kw: str, present: dict[str, bool]
) -> dict[str, Any]:
    """Concrete replacement copy for every slot missing the keyword."""
    title = page.title or ""
    meta = page.meta_description or ""
    h1 = page.h1[0] if page.h1 else ""
    brand = title.split("—")[0].split("|")[0].strip() or "Your brand"
    out: dict[str, Any] = {}

    if not present["title"]:
        suggested = f"{kw.title()} — {brand}" if title else f"{kw.title()} | {brand}"
        if title and len(f"{brand} — {kw.title()}") <= TITLE_MAX:
            suggested = f"{brand} — {kw.title()}"
        out["title"] = {
            "current": title or None,
            "current_length": len(title),
            "suggested": suggested[:TITLE_MAX],
            "suggested_length": len(suggested[:TITLE_MAX]),
            "why": f'Primary keyword "{kw}" was absent from the <title>.',
        }

    if not present["meta_description"]:
        base = meta.rstrip(".") if meta else f"{brand} helps you get more from {kw}"
        suggested = f"{base}. Learn how {brand} supports {kw}."
        out["meta_description"] = {
            "current": meta or None,
            "current_length": len(meta),
            "suggested": suggested[:META_MAX],
            "suggested_length": len(suggested[:META_MAX]),
            "why": f'Meta description did not mention "{kw}".',
        }

    if not present["h1"]:
        suggested = f"{h1.rstrip('.')} — {kw.title()}" if h1 else f"{kw.title()} for {brand}"
        out["h1"] = {
            "current": h1 or None,
            "suggested": suggested,
            "why": (
                f'Your H1 does not include "{kw}".'
                if h1
                else "Page has no H1 at all; add one containing the primary keyword."
            ),
        }

    if not present["h2"]:
        out["h2_addition"] = {
            "suggested": f"How {brand} helps with {kw}",
            "why": f'No H2 supports "{kw}"; add a section heading so the topic is scannable.',
        }

    if not present["body"]:
        out["body"] = {
            "suggested": (
                f"Add a paragraph on this page that explains {kw} in the context of "
                f"{brand}'s actual offering, using the phrase \"{kw}\" naturally 2–3 times."
            ),
            "why": f'"{kw}" does not appear anywhere in the rendered body copy.',
        }
    return out
