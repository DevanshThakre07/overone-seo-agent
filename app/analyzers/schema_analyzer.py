"""Detect JSON-LD structured data — coverage + richer homepage/type checks."""

from __future__ import annotations

from app.analyzers.base import AnalysisContext
from app.models.issues import AnalyzerResult, Issue, Severity
from app.utils.url import normalize_url

# Cap untyped/detail issues so chat/reports stay readable.
_MAX_DETAIL_ISSUES = 5

_REQUIRED_PROPS: dict[str, tuple[str, ...]] = {
    "Organization": ("name",),
    "WebSite": ("name",),  # url also useful; name is the usual empty case
    "Article": ("headline",),
    "BlogPosting": ("headline",),
    "Product": ("name",),
}


def _normalize_type(t: str) -> str:
    s = (t or "").strip()
    if "/" in s:
        s = s.rstrip("/").split("/")[-1]
    return s


def _suggested_schema_types(
    url: str,
    *,
    title: str = "",
    h1: str = "",
    is_seed: bool = False,
) -> dict[str, object]:
    """Map page template → recommended schema.org types (advisor, not inventing markup)."""
    blob = f"{url} {title} {h1}".lower()
    try:
        from urllib.parse import urlsplit

        path = (urlsplit(url).path or "/").lower()
    except Exception:  # noqa: BLE001
        path = url.lower()

    if is_seed or path in {"", "/"}:
        return {
            "kind": "home",
            "types": ["Organization", "WebSite"],
            "why": "Home pages should declare the brand (Organization) and site entity (WebSite).",
        }
    if any(k in path or k in blob for k in ("privacy", "terms", "tos", "legal")):
        return {
            "kind": "legal",
            "types": ["WebPage"],
            "why": "Legal pages usually need only WebPage (or none) — avoid Product/FAQ here.",
        }
    if any(k in path for k in ("blog", "article", "post", "news", "guide")):
        return {
            "kind": "article",
            "types": ["Article", "BlogPosting"],
            "why": "Editorial URLs benefit from Article/BlogPosting with headline and author.",
        }
    if any(k in path or k in blob for k in ("product", "pricing", "shop", "buy")):
        return {
            "kind": "product",
            "types": ["Product", "Offer"],
            "why": "Commercial pages should expose Product (and Offer when price is public).",
        }
    if any(k in path or k in blob for k in ("faq", "help", "support")):
        return {
            "kind": "faq",
            "types": ["FAQPage"],
            "why": "Q&A hubs can use FAQPage when questions/answers are visible on-page.",
        }
    if any(k in path for k in ("about", "contact")):
        return {
            "kind": "about",
            "types": ["AboutPage", "Organization"],
            "why": "About/contact pages can use AboutPage and link the Organization entity.",
        }
    return {
        "kind": "generic",
        "types": ["WebPage"],
        "why": "Generic URLs: WebPage is enough unless the template is Article/Product/FAQ.",
    }


class SchemaAnalyzer:
    """Detect JSON-LD structured data and report discovered schema types."""

    name = "schema"

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        issues: list[Issue] = []
        missing = 0
        pages_with_schema = 0
        type_counts: dict[str, int] = {}
        untyped_urls: list[str] = []
        analyzed = 0
        parse_error_pages = 0
        seed_norm = normalize_url(context.seed_url)
        seed_missing = False
        seed_types: set[str] = set()

        for page in context.pages:
            if page.is_broken:
                continue
            analyzed += 1
            page_norm = normalize_url(page.final_url or page.url)
            parse_errors = int(getattr(page, "json_ld_parse_errors", 0) or 0)
            warnings = page.extraction_warnings or []
            if parse_errors or "json_ld_present_but_unparsed" in warnings:
                parse_error_pages += 1
                if parse_error_pages <= _MAX_DETAIL_ISSUES:
                    issues.append(
                        Issue(
                            code="schema_parse_error",
                            severity=Severity.WARNING,
                            message=(
                                "JSON-LD script present but could not be fully parsed. "
                                "Fix invalid JSON in application/ld+json."
                            ),
                            url=page.final_url,
                            details={
                                "json_ld_parse_errors": parse_errors
                                or len(
                                    [
                                        b
                                        for b in (page.json_ld_blocks or [])
                                        if not b.get("ok")
                                    ]
                                ),
                                "script_count": getattr(
                                    page, "json_ld_script_count", None
                                ),
                            },
                        )
                    )

            if not page.has_json_ld and not page.schema_types and parse_errors == 0:
                missing += 1
                if page_norm == seed_norm:
                    seed_missing = True
                # Plan Perfect PP-6: recommend concrete types for this page template
                if (
                    len([i for i in issues if i.code == "schema_type_suggested"])
                    < _MAX_DETAIL_ISSUES
                ):
                    suggested = _suggested_schema_types(
                        page.final_url or page.url,
                        title=page.title or "",
                        h1=(page.h1[0] if page.h1 else ""),
                        is_seed=(page_norm == seed_norm),
                    )
                    issues.append(
                        Issue(
                            code="schema_type_suggested",
                            severity=Severity.INFO,
                            message=(
                                f"No JSON-LD on this page. Recommended @type(s): "
                                f"{', '.join(suggested['types'])}. {suggested['why']}"
                            ),
                            url=page.final_url,
                            details={
                                "page_kind": suggested["kind"],
                                "recommended_types": suggested["types"],
                                "why": suggested["why"],
                            },
                        )
                    )
                continue

            if page.schema_types or page.has_json_ld:
                pages_with_schema += 1
            if page.schema_types:
                if page_norm == seed_norm:
                    seed_types = {_normalize_type(t) for t in page.schema_types}
                for schema_type in page.schema_types:
                    key = _normalize_type(schema_type)
                    type_counts[key] = type_counts.get(key, 0) + 1
                    if not key:
                        if len([i for i in issues if i.code == "invalid_schema_type"]) < _MAX_DETAIL_ISSUES:
                            issues.append(
                                Issue(
                                    code="invalid_schema_type",
                                    severity=Severity.INFO,
                                    message="JSON-LD @type is empty or invalid",
                                    url=page.final_url,
                                    details={"raw_type": schema_type},
                                )
                            )
            elif page.has_json_ld or parse_errors:
                untyped_urls.append(page.final_url)

            # Required-ish props on shallow blocks
            for block in (page.json_ld_blocks or [])[:5]:
                if not block.get("ok"):
                    continue
                props_wrap = block.get("props") or {}
                for obj in props_wrap.get("objects") or []:
                    obj_types = [_normalize_type(t) for t in (obj.get("types") or [])]
                    props = obj.get("props") or {}
                    for t in obj_types:
                        required = _REQUIRED_PROPS.get(t)
                        if not required:
                            continue
                        for field in required:
                            val = props.get(field)
                            empty = val is None or (
                                isinstance(val, str) and not val.strip()
                            )
                            # Only flag when the object looks like that type and
                            # field is missing/empty (not when props stripped).
                            if empty and (
                                field in props or not props
                            ):
                                # If props dict is empty we can't know — skip
                                if not props:
                                    continue
                                if (
                                    len(
                                        [
                                            i
                                            for i in issues
                                            if i.code == "schema_empty_required"
                                        ]
                                    )
                                    >= _MAX_DETAIL_ISSUES
                                ):
                                    continue
                                issues.append(
                                    Issue(
                                        code="schema_empty_required",
                                        severity=Severity.INFO,
                                        message=(
                                            f"{t} schema is missing/empty "
                                            f"recommended field `{field}`."
                                        ),
                                        url=page.final_url,
                                        details={
                                            "schema_type": t,
                                            "field": field,
                                        },
                                    )
                                )

        if analyzed > 0 and missing > 0:
            coverage = pages_with_schema / analyzed
            if seed_missing:
                issues.append(
                    Issue(
                        code="missing_schema",
                        severity=Severity.INFO,
                        message=(
                            "Seed/home page has no JSON-LD structured data. "
                            "Add Organization and WebSite schema at minimum."
                        ),
                        url=context.seed_url,
                    )
                )
            if missing > 1 or (missing == 1 and not seed_missing):
                issues.append(
                    Issue(
                        code="schema_coverage_low"
                        if coverage < 0.5
                        else "schema_partial",
                        severity=Severity.INFO,
                        message=(
                            f"{missing}/{analyzed} crawled pages lack JSON-LD "
                            f"({coverage:.0%} coverage). Prefer meaningful types "
                            "(Organization, WebSite, Article, Product, FAQ) on "
                            "key templates — not every URL needs schema."
                        ),
                        url=context.seed_url,
                        details={
                            "pages_missing_schema": missing,
                            "pages_analyzed": analyzed,
                            "coverage": round(coverage, 3),
                        },
                    )
                )

        # Homepage recommended types when some schema exists
        if not seed_missing and seed_types:
            if "Organization" not in seed_types and "LocalBusiness" not in seed_types:
                issues.append(
                    Issue(
                        code="missing_organization_schema",
                        severity=Severity.INFO,
                        message=(
                            "Home page JSON-LD is present but missing Organization "
                            "(recommended for brand entity)."
                        ),
                        url=context.seed_url,
                        details={"seed_types": sorted(seed_types)},
                    )
                )
            if "WebSite" not in seed_types:
                issues.append(
                    Issue(
                        code="missing_website_schema",
                        severity=Severity.INFO,
                        message=(
                            "Home page JSON-LD is present but missing WebSite "
                            "(recommended for sitelinks / site entity)."
                        ),
                        url=context.seed_url,
                        details={"seed_types": sorted(seed_types)},
                    )
                )

        for url in untyped_urls[:_MAX_DETAIL_ISSUES]:
            issues.append(
                Issue(
                    code="schema_untyped",
                    severity=Severity.INFO,
                    message="JSON-LD found but no @type values were detected",
                    url=url,
                )
            )

        return AnalyzerResult(
            analyzer=self.name,
            issues=issues,
            metrics={
                "pages_missing_schema": missing,
                "pages_with_schema": pages_with_schema,
                "pages_analyzed": analyzed,
                "schema_types": type_counts,
                "unique_schema_types": len(type_counts),
                "untyped_count": len(untyped_urls),
                "pages_with_parse_errors": parse_error_pages,
                "seed_has_organization": "Organization" in seed_types
                or "LocalBusiness" in seed_types,
                "seed_has_website": "WebSite" in seed_types,
            },
        )
