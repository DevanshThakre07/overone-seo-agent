"""Prescriptive on-page recommendations — concrete rewrite copy, not generic advice."""

from __future__ import annotations

import re
from typing import Any

from app.models.page import PageExtraction

TITLE_MIN, TITLE_MAX = 30, 60
META_MIN, META_MAX = 70, 160


def build_prescriptive_recommendations(pages: list[PageExtraction]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in pages:
        if page.is_broken:
            continue
        unreliable = bool((page.seo_signals or {}).get("likely_js_shell")) and not page.js_rendered
        title = (page.title or "").strip()
        meta = (page.meta_description or "").strip()
        h1 = (page.h1[0].strip() if page.h1 else "")
        topic = h1 or title or page.og_title or "this page"
        page_kind = _page_kind(page.final_url, title=title, h1=h1)

        rec: dict[str, Any] = {
            "url": page.final_url,
            "rendering_unreliable": unreliable,
            "page_kind": page_kind,
            "current": {
                "title": title or None,
                "meta_description": meta or None,
                "h1": h1 or None,
            },
            "suggested_title": None,
            "suggested_meta_description": None,
            "suggested_h1": None,
            "rewrites": {},
            "actions": [],
        }
        if unreliable:
            rec["actions"].append(
                _action(
                    "enable_js_rendering",
                    (
                        "Do not apply on-page copy changes until Playwright captures "
                        "the rendered DOM — current body/heading data is from an unrendered JS shell."
                    ),
                    url=page.final_url,
                    field="rendering",
                    current="js_shell_unrendered",
                )
            )
            out.append(rec)
            continue

        # Always produce concrete rewrite candidates (same spirit as optimize_page).
        secondary = (page.h2[0].strip() if page.h2 else "") or meta
        suggested_title = _rewrite_title(title, topic, secondary, page_kind=page_kind)
        suggested_meta = _rewrite_meta(
            meta, topic, title or suggested_title, page_kind=page_kind
        )
        suggested_h1 = h1 if h1 else _trim(topic, 70)

        rec["suggested_title"] = suggested_title
        rec["suggested_meta_description"] = suggested_meta
        rec["suggested_h1"] = suggested_h1
        rec["rewrites"] = {
            "title": {
                "current": title or "(missing)",
                "suggested": suggested_title,
                "current_length": len(title),
                "suggested_length": len(suggested_title),
            },
            "meta_description": {
                "current": meta or "(missing)",
                "suggested": suggested_meta,
                "current_length": len(meta),
                "suggested_length": len(suggested_meta),
            },
            "h1": {
                "current": h1 or "(missing)",
                "suggested": suggested_h1,
            },
        }

        if not title:
            rec["actions"].append(
                _action(
                    "missing_title",
                    f'Replace missing <title> with: "{suggested_title}" ({len(suggested_title)} chars)',
                    url=page.final_url,
                    field="title",
                    current=None,
                    suggested=suggested_title,
                )
            )
        elif title == suggested_title and len(title) < TITLE_MIN:
            rec["actions"].append(
                _action(
                    "title_too_short_needs_copy",
                    (
                        f'Title is {len(title)} chars — short for search results '
                        f"(aim {TITLE_MIN}–{TITLE_MAX}). Everything on the page already "
                        f'repeats it, so add a real value proposition, e.g. '
                        f'"{title} — <primary benefit or category>" '
                        f"(up to {TITLE_MAX - len(title) - 3} more chars). "
                        "No filler was invented for you."
                    ),
                    url=page.final_url,
                    field="title",
                    current=title,
                    suggested=None,
                    char_budget=TITLE_MAX - len(title) - 3,
                )
            )
        elif title != suggested_title:
            reason = (
                "too short" if len(title) < TITLE_MIN else
                "too long" if len(title) > TITLE_MAX else
                "can be clearer for SEO"
            )
            rec["actions"].append(
                _action(
                    "title_rewrite",
                    (
                        f'Title is {reason} ({len(title)} chars). '
                        f'Use: "{suggested_title}" ({len(suggested_title)} chars)'
                    ),
                    url=page.final_url,
                    field="title",
                    current=title,
                    suggested=suggested_title,
                )
            )

        if not meta:
            rec["actions"].append(
                _action(
                    "missing_meta_description",
                    (
                        f'Replace missing meta description with: "{suggested_meta}" '
                        f"({len(suggested_meta)} chars)"
                    ),
                    url=page.final_url,
                    field="meta_description",
                    current=None,
                    suggested=suggested_meta,
                )
            )
        elif meta != suggested_meta:
            reason = (
                "too short" if len(meta) < META_MIN else
                "too long" if len(meta) > META_MAX else
                "can be clearer for SEO"
            )
            rec["actions"].append(
                _action(
                    "meta_rewrite",
                    (
                        f'Meta description is {reason} ({len(meta)} chars). '
                        f'Use: "{suggested_meta}" ({len(suggested_meta)} chars)'
                    ),
                    url=page.final_url,
                    field="meta_description",
                    current=meta,
                    suggested=suggested_meta,
                )
            )

        if not h1:
            rec["actions"].append(
                _action(
                    "missing_h1",
                    f'Replace missing H1 with: "{suggested_h1}"',
                    url=page.final_url,
                    field="h1",
                    current=None,
                    suggested=suggested_h1,
                )
            )
        elif len(page.h1) > 1:
            rec["actions"].append(
                _action(
                    "multiple_h1",
                    (
                        f'Keep a single H1. Prefer: "{h1}". '
                        f"Convert extras to H2: {', '.join(repr(x) for x in page.h1[1:3])}"
                    ),
                    url=page.final_url,
                    field="h1",
                    current=h1,
                    suggested=h1,
                )
            )

        if not page.canonical:
            rec["actions"].append(
                _action(
                    "missing_canonical",
                    f'Add: <link rel="canonical" href="{page.final_url}" />',
                    url=page.final_url,
                    field="canonical",
                    current=None,
                    suggested=page.final_url,
                )
            )

        if page.images:
            # alt="" is a valid decorative marker, and <source> takes no alt.
            missing = [
                img.src
                for img in page.images
                if not img.alt_present and not img.decorative and not img.is_source
            ]
            for src in missing[:5]:
                filename = src.rstrip("/").split("/")[-1] or "image"
                alt = (
                    filename.rsplit(".", 1)[0]
                    .replace("-", " ")
                    .replace("_", " ")
                    .strip()
                    .title()
                )
                rec["actions"].append(
                    _action(
                        "missing_image_alt",
                        f'Set alt="{alt}" on image {src}',
                        url=page.final_url,
                        field="img_alt",
                        current=None,
                        suggested=alt,
                        src=src,
                    )
                )

        out.append(rec)
    return out


def merge_gsc_into_recommendations(
    recommendations: list[dict[str, Any]],
    gsc_block: dict[str, Any] | None,
    *,
    max_actions_per_page: int = 5,
) -> list[dict[str, Any]]:
    """Attach Search Console opportunities as actions on matching page recs.

    When GSC status is not ``ok`` or there are no opportunities, returns
    recommendations unchanged. Pages that appear only in GSC (not crawled)
    get a lightweight recommendation stub so opportunities are not dropped.
    """
    if not gsc_block or gsc_block.get("status") != "ok":
        return recommendations

    snapshot = gsc_block.get("snapshot") or {}
    opportunities = list(snapshot.get("opportunities") or [])
    if not opportunities:
        return recommendations

    by_url: dict[str, dict[str, Any]] = {
        _norm_page_url(str(rec.get("url") or "")): rec for rec in recommendations if rec.get("url")
    }
    # Preserve insertion order of existing recs; append stubs at end.
    out = list(recommendations)
    actions_added_for: dict[str, int] = {}

    for opp in opportunities:
        page_url = str(opp.get("page") or "")
        if not page_url:
            continue
        key = _norm_page_url(page_url)
        rec = by_url.get(key)
        if rec is None:
            rec = {
                "url": page_url,
                "rendering_unreliable": False,
                "current": {"title": None, "meta_description": None, "h1": None},
                "suggested_title": None,
                "suggested_meta_description": None,
                "suggested_h1": None,
                "rewrites": {},
                "actions": [],
                "source": "google_search_console",
            }
            by_url[key] = rec
            out.append(rec)

        count = actions_added_for.get(key, 0)
        if count >= max_actions_per_page:
            continue

        action = _gsc_opportunity_action(opp)
        if action is None:
            continue
        rec.setdefault("actions", []).append(action)
        actions_added_for[key] = count + 1

    return out


def _gsc_opportunity_action(opp: dict[str, Any]) -> dict[str, Any] | None:
    query = (opp.get("query") or "").strip()
    if not query:
        return None
    kind = opp.get("kind") or "page2"
    impressions = int(opp.get("impressions") or 0)
    position = float(opp.get("position") or 0)
    ctr = float(opp.get("ctr") or 0)
    why = opp.get("why") or ""

    if kind == "low_ctr":
        code = "gsc_low_ctr"
        message = (
            f'GSC low CTR: query "{query}" at position {position:.1f} '
            f"({impressions} impressions, CTR {ctr:.1%}). {why} "
            f'Target this query in the title/meta for {opp.get("page")}.'
        )
    else:
        code = "gsc_page2_opportunity"
        message = (
            f'GSC page-2 opportunity: query "{query}" at position {position:.1f} '
            f"({impressions} impressions, CTR {ctr:.1%}). {why}"
        )

    return {
        "code": code,
        "message": message,
        "query": query,
        "page": opp.get("page"),
        "impressions": impressions,
        "clicks": int(opp.get("clicks") or 0),
        "ctr": ctr,
        "position": position,
        "kind": kind,
        "source": "google_search_console",
        "suggested_value": None,
        "evidence": {
            "url": opp.get("page"),
            "field": "gsc_query",
            "current_value": (
                f'query="{query}" pos={position:.1f} impr={impressions} ctr={ctr:.1%}'
            ),
            "suggested_value": None,
        },
    }


def _action(
    code: str,
    message: str,
    *,
    url: str,
    field: str | None = None,
    current: Any = None,
    suggested: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    """Recommendation action with explicit evidence (accuracy rule for Plan Perfect)."""
    row: dict[str, Any] = {
        "code": code,
        "message": message,
        "evidence": {
            "url": url,
            "field": field,
            "current_value": current,
            "suggested_value": suggested,
        },
    }
    if suggested is not None:
        row["suggested_value"] = suggested
    if current is not None:
        row["current_value"] = current
    row.update(extra)
    return row


def _page_kind(url: str, *, title: str = "", h1: str = "") -> str:
    """Classify page type so rewrites stay accurate (no homepage marketing on /privacy)."""
    blob = f"{url} {title} {h1}".lower()
    path = ""
    try:
        from urllib.parse import urlsplit

        path = (urlsplit(url).path or "/").lower()
    except Exception:  # noqa: BLE001
        path = url.lower()
    if any(k in path or k in blob for k in ("privacy", "privacypolicy")):
        return "privacy"
    if any(k in path or k in blob for k in ("terms", "tos", "legal")):
        return "legal"
    if any(k in path for k in ("blog", "article", "post", "news")):
        return "article"
    if any(k in path for k in ("product", "pricing", "shop")):
        return "product"
    if path in {"", "/"}:
        return "home"
    return "generic"


def _norm_page_url(url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit((url or "").strip())
    if not parts.scheme and not parts.netloc:
        return url.rstrip("/") or url
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _key(text: str) -> str:
    """Comparison key: case/punctuation/whitespace-insensitive."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _is_redundant(addition: str, existing: str) -> bool:
    a, e = _key(addition), _key(existing)
    return bool(a) and (a in e or e in a)


def _rewrite_title(
    title: str, topic: str, secondary: str = "", *, page_kind: str = "generic"
) -> str:
    if not title:
        if page_kind == "privacy":
            return _fit(f"Privacy Policy | {topic}", TITLE_MIN, TITLE_MAX)
        if page_kind == "legal":
            return _fit(f"Terms of Service | {topic}", TITLE_MIN, TITLE_MAX)
        return _fit(f"{topic} | Official Site", TITLE_MIN, TITLE_MAX)
    if TITLE_MIN <= len(title) <= TITLE_MAX:
        return title
    if len(title) < TITLE_MIN:
        # Only append material the title does not already say, and only if it
        # fits whole. Previously this produced
        # "Actoro — Read less, Live more — Read less, live more.".
        for addition in (topic, secondary):
            if addition and not _is_redundant(addition, title):
                candidate = f"{title} — {addition}"
                if len(candidate) <= TITLE_MAX:
                    return _fit(candidate, TITLE_MIN, TITLE_MAX)
        # Nothing genuine to add — leave it alone rather than pad with filler.
        return title
    return _trim(title, TITLE_MAX)


def _rewrite_meta(
    meta: str, topic: str, title: str, *, page_kind: str = "generic"
) -> str:
    # Legal/policy pages must not inherit homepage marketing copy.
    if page_kind == "privacy":
        base = meta or f"How {topic} collects, uses, and protects personal data."
        if not meta or len(meta) < META_MIN:
            text = f"{base.rstrip(' .')}. Read the full privacy policy for details."
            return _trim(text, META_MAX) if len(text) > META_MAX else text
        if len(meta) > META_MAX:
            return _trim(meta, META_MAX)
        return meta
    if page_kind == "legal":
        base = meta or f"Terms that govern use of {topic}."
        if not meta or len(meta) < META_MIN:
            text = f"{base.rstrip(' .')}. Review the full terms before using the service."
            return _trim(text, META_MAX) if len(text) > META_MAX else text
        if len(meta) > META_MAX:
            return _trim(meta, META_MAX)
        return meta

    if not meta:
        return _fit(
            f"{topic}: learn what it offers, key benefits, and how to get started today.",
            META_MIN,
            META_MAX,
        )
    if META_MIN <= len(meta) <= META_MAX:
        return meta
    if len(meta) < META_MIN:
        # Keep the tail generic: splicing the H1 in as a noun phrase reads badly
        # ("See how Read less, live more. works").
        base = meta.rstrip(" .")
        return _fit(
            f"{base}. See how it works, what you get, and how to start in minutes.",
            META_MIN,
            META_MAX,
        )
    return _trim(meta, META_MAX)


def _fit(text: str, minimum: int, maximum: int) -> str:
    text = " ".join(text.split())
    if len(text) > maximum:
        return _trim(text, maximum)
    fillers = [
        " — Complete Guide",
        " | Official Overview",
        " for Beginners",
        " and Key Benefits",
    ]
    i = 0
    while len(text) < minimum and i < len(fillers):
        candidate = text + fillers[i]
        if len(candidate) <= maximum and not _is_redundant(fillers[i], text):
            text = candidate
        i += 1
    # Returning slightly-short but readable copy beats padding with filler words.
    return text


def _trim(text: str, maximum: int) -> str:
    text = " ".join(text.split())
    if len(text) <= maximum:
        return text
    cut = text[: maximum - 1].rsplit(" ", 1)[0]
    return (cut or text[: maximum - 1]).rstrip(" ,;-") + "…"
