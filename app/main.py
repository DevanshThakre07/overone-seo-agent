"""CLI entrypoints: seo-audit / seo-optimize / seo-report / seo-history / seo-compare."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config.settings import get_settings
from app.logging import setup_logging
from app.tools.audit_tool import audit_site
from app.tools.compare_tool import generate_change_report
from app.tools.history_tool import list_history
from app.tools.optimize_tool import optimize_page
from app.tools.report_tool import generate_report


def _parse_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def build_audit_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seo-audit",
        description="Crawl a website and produce a structured SEO audit JSON report.",
    )
    parser.add_argument("url", help="Seed URL to audit")
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        help="Write JSON report to this file (also prints to stdout)",
    )
    parser.add_argument("--max-pages", type=int, default=None, help="Override max pages")
    parser.add_argument("--max-depth", type=int, default=None, help="Override max depth")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist audit via repository (SQLite)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare against previous saved audit (also saves current audit)",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run Phase 2 AI optimization on crawled pages (requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--keywords",
        default=None,
        help="Comma-separated target keywords for AI optimization",
    )
    parser.add_argument(
        "--optimize-max-pages",
        type=int,
        default=None,
        help="Max pages to optimize when --optimize is set",
    )
    return parser


def build_optimize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seo-optimize",
        description="Generate AI SEO improvement suggestions for a single page.",
    )
    parser.add_argument("url", help="Page URL to optimize")
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        help="Write JSON suggestions to this file (also prints to stdout)",
    )
    parser.add_argument(
        "--keywords",
        default=None,
        help="Comma-separated target keywords",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_audit_parser().parse_args(argv)
    settings = get_settings()
    setup_logging(level=settings.logging.level, json_logs=settings.logging.json_logs)

    audit = audit_site(
        args.url,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        save=args.save,
        compare=args.compare,
        optimize=args.optimize,
        target_keywords=_parse_keywords(args.keywords),
        optimize_max_pages=args.optimize_max_pages,
    )
    payload = audit.model_dump_json(indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")

    print(payload)
    return 0


def optimize_main(argv: list[str] | None = None) -> int:
    args = build_optimize_parser().parse_args(argv)
    settings = get_settings()
    setup_logging(level=settings.logging.level, json_logs=settings.logging.json_logs)

    result = optimize_page(args.url, target_keywords=_parse_keywords(args.keywords) or None)
    payload = result.model_dump_json(indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")

    print(payload)
    return 0 if result.status in {"ok", "partial"} else 1


def build_report_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seo-report",
        description="Generate a downloadable SEO report (markdown or json).",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Crawl/audit this URL then render a report")
    source.add_argument("--audit-id", help="Render a report from a saved audit id")
    parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "json", "pdf"],
        default="markdown",
        help="Report format (pdf not implemented yet)",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        help="Write report to this file (also prints to stdout)",
    )
    parser.add_argument("--max-pages", type=int, default=None, help="Override max pages")
    parser.add_argument(
        "--full-audit-json",
        action="store_true",
        help="When format=json, emit the full SiteAudit instead of ReportDocument",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist audit when generating from --url",
    )
    return parser


def report_main(argv: list[str] | None = None) -> int:
    args = build_report_parser().parse_args(argv)
    settings = get_settings()
    setup_logging(level=settings.logging.level, json_logs=settings.logging.json_logs)

    try:
        artifact = generate_report(
            url=args.url,
            audit_id=args.audit_id,
            format=args.format,
            full_audit_json=args.full_audit_json,
            out=args.out,
            max_pages=args.max_pages,
            save=args.save,
        )
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(artifact.content)
    return 0


def build_history_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seo-history",
        description="List previously saved SEO audits for a URL.",
    )
    parser.add_argument("url", help="Site URL")
    parser.add_argument("--limit", type=int, default=20, help="Max audits to return")
    parser.add_argument("-o", "--out", type=Path, help="Write JSON history to file")
    return parser


def history_main(argv: list[str] | None = None) -> int:
    args = build_history_parser().parse_args(argv)
    settings = get_settings()
    setup_logging(level=settings.logging.level, json_logs=settings.logging.json_logs)

    result = list_history(args.url, limit=args.limit)
    payload = result.model_dump_json(indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


def build_compare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seo-compare",
        description="Audit a site and generate a change report vs the previous audit.",
    )
    parser.add_argument("url", help="Site URL")
    parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Change report format",
    )
    parser.add_argument("-o", "--out", type=Path, help="Write change report to file")
    parser.add_argument("--max-pages", type=int, default=None, help="Override max pages")
    return parser


def compare_main(argv: list[str] | None = None) -> int:
    args = build_compare_parser().parse_args(argv)
    settings = get_settings()
    setup_logging(level=settings.logging.level, json_logs=settings.logging.json_logs)

    content = generate_change_report(
        args.url,
        format=args.format,
        max_pages=args.max_pages,
        out=args.out,
    )
    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
