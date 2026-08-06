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

        rec: dict[str, Any] = {
            "url": page.final_url,
            "rendering_unreliable": unreliable,
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
                {
                    "code": "enable_js_rendering",
                    "message": (
                        "Do not apply on-page copy changes until Playwright captures "
                        "the rendered DOM — current body/heading data is from an unrendered JS shell."
                    ),
                }
            )
            out.append(rec)
            continue

        # Always produce concrete rewrite candidates (same spirit as optimize_page).
        secondary = (page.h2[0].strip() if page.h2 else "") or meta
        suggested_title = _rewrite_title(title, topic, secondary)
        suggested_meta = _rewrite_meta(meta, topic, title or suggested_title)
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
                {
                    "code": "missing_title",
                    "message": f'Replace missing <title> with: "{suggested_title}" ({len(suggested_title)} chars)',
                    "suggested_value": suggested_title,
                }
            )
        elif title == suggested_title and len(title) < TITLE_MIN:
            # Be explicit rather than emitting filler copy or staying silent.
            rec["actions"].append(
                {
                    "code": "title_too_short_needs_copy",
                    "message": (
                        f'Title is {len(title)} chars — short for search results '
                        f"(aim {TITLE_MIN}–{TITLE_MAX}). Everything on the page already "
                        f'repeats it, so add a real value proposition, e.g. '
                        f'"{title} — <primary benefit or category>" '
                        f"(up to {TITLE_MAX - len(title) - 3} more chars). "
                        "No filler was invented for you."
                    ),
                    "current_value": title,
                    "char_budget": TITLE_MAX - len(title) - 3,
                }
            )
        elif title != suggested_title:
            reason = (
                "too short" if len(title) < TITLE_MIN else
                "too long" if len(title) > TITLE_MAX else
                "can be clearer for SEO"
            )
            rec["actions"].append(
                {
                    "code": "title_rewrite",
                    "message": (
                        f'Title is {reason} ({len(title)} chars). '
                        f'Use: "{suggested_title}" ({len(suggested_title)} chars)'
                    ),
                    "current_value": title,
                    "suggested_value": suggested_title,
                }
            )

        if not meta:
            rec["actions"].append(
                {
                    "code": "missing_meta_description",
                    "message": (
                        f'Replace missing meta description with: "{suggested_meta}" '
                        f"({len(suggested_meta)} chars)"
                    ),
                    "suggested_value": suggested_meta,
                }
            )
        elif meta != suggested_meta:
            reason = (
                "too short" if len(meta) < META_MIN else
                "too long" if len(meta) > META_MAX else
                "can be clearer for SEO"
            )
            rec["actions"].append(
                {
                    "code": "meta_rewrite",
                    "message": (
                        f'Meta description is {reason} ({len(meta)} chars). '
                        f'Use: "{suggested_meta}" ({len(suggested_meta)} chars)'
                    ),
                    "current_value": meta,
                    "suggested_value": suggested_meta,
                }
            )

        if not h1:
            rec["actions"].append(
                {
                    "code": "missing_h1",
                    "message": f'Replace missing H1 with: "{suggested_h1}"',
                    "suggested_value": suggested_h1,
                }
            )
        elif len(page.h1) > 1:
            rec["actions"].append(
                {
                    "code": "multiple_h1",
                    "message": (
                        f'Keep a single H1. Prefer: "{h1}". '
                        f"Convert extras to H2: {', '.join(repr(x) for x in page.h1[1:3])}"
                    ),
                    "suggested_value": h1,
                }
            )

        if not page.canonical:
            rec["actions"].append(
                {
                    "code": "missing_canonical",
                    "message": f'Add: <link rel="canonical" href="{page.final_url}" />',
                    "suggested_value": page.final_url,
                }
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
                    {
                        "code": "missing_image_alt",
                        "message": f'Set alt="{alt}" on image {src}',
                        "suggested_value": alt,
                        "src": src,
                    }
                )

        out.append(rec)
    return out


def _key(text: str) -> str:
    """Comparison key: case/punctuation/whitespace-insensitive."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _is_redundant(addition: str, existing: str) -> bool:
    a, e = _key(addition), _key(existing)
    return bool(a) and (a in e or e in a)


def _rewrite_title(title: str, topic: str, secondary: str = "") -> str:
    if not title:
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


def _rewrite_meta(meta: str, topic: str, title: str) -> str:
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
