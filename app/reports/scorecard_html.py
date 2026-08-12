"""Thin client scorecard HTML for public share links (FP-4)."""

from __future__ import annotations

import html
from typing import Any

from app.models.audit import SiteAudit
from app.models.issues import Severity


def render_scorecard_html(
    audit: SiteAudit,
    *,
    token: str,
    expires_at: Any = None,
) -> str:
    """Client-facing scorecard: score, counts, top issues, CTA for PDF.

    Intentionally thin — not a full operator dashboard clone.
    """
    seed = html.escape(audit.seed_url or "")
    audit_id = html.escape(audit.audit_id or "")
    token_esc = html.escape(token)
    expires = html.escape(str(expires_at or "—"))
    score = float(audit.score or 0)
    score_label = f"{score:.0f}" if score == int(score) else f"{score:.1f}"

    summary = audit.summary or {}
    counts = summary.get("severity_counts") or {}
    if not counts:
        counts = {
            "critical": sum(1 for i in audit.issues if i.severity == Severity.CRITICAL),
            "warning": sum(1 for i in audit.issues if i.severity == Severity.WARNING),
            "info": sum(1 for i in audit.issues if i.severity == Severity.INFO),
        }
    critical = int(counts.get("critical") or 0)
    warning = int(counts.get("warning") or 0)
    info = int(counts.get("info") or 0)
    pages_n = len(audit.pages or [])

    # Prefer critical, then warning; cap for a scannable client page.
    ordered = sorted(
        audit.issues or [],
        key=lambda i: (
            0 if i.severity == Severity.CRITICAL else 1 if i.severity == Severity.WARNING else 2,
            i.code or "",
        ),
    )
    top = ordered[:12]
    issue_rows = []
    for issue in top:
        sev = html.escape(issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity))
        code = html.escape(issue.code or "")
        msg = html.escape(issue.message or "")
        url = html.escape(issue.url or "")
        url_html = f'<span class="url">{url}</span>' if url else ""
        issue_rows.append(
            f'<li class="issue sev-{sev}">'
            f'<span class="pill">{sev}</span> '
            f"<code>{code}</code> "
            f'<span class="msg">{msg}</span>'
            f"{url_html}"
            f"</li>"
        )
    issues_html = (
        "<ul class=\"issues\">" + "".join(issue_rows) + "</ul>"
        if issue_rows
        else '<p class="empty">No issues recorded for this crawl.</p>'
    )

    # Light recommendations peek (first page, first few actions) — evidence if present.
    rec_bits: list[str] = []
    for rec in (summary.get("recommendations") or [])[:3]:
        if not isinstance(rec, dict):
            continue
        page_url = html.escape(str(rec.get("url") or ""))
        for action in (rec.get("actions") or [])[:2]:
            if not isinstance(action, dict):
                continue
            msg = html.escape(str(action.get("message") or action.get("code") or ""))
            if not msg:
                continue
            rec_bits.append(f"<li><span class=\"page\">{page_url}</span> {msg}</li>")
        if len(rec_bits) >= 6:
            break
    recs_html = (
        "<ul class=\"recs\">" + "".join(rec_bits) + "</ul>"
        if rec_bits
        else '<p class="empty">Recommendations were not attached to this saved audit summary.</p>'
    )

    ring = max(0, min(100, score))
    # SVG ring: circumference ~ 2πr with r=54 → ~339
    circ = 339.292
    dash = circ * (ring / 100.0)

    created = html.escape(str(getattr(audit, "created_at", "") or ""))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SEO Scorecard — {seed}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;700&family=Figtree:wght@400;550;650&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --ink: #10231c;
      --muted: #5a6b64;
      --paper: #f3f7f5;
      --card: #ffffff;
      --line: #d5e0db;
      --accent: #0f6b5c;
      --accent-soft: #d7ebe3;
      --crit: #9b2c2c;
      --warn: #9a6700;
      --info: #3d5a80;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Figtree, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(900px 420px at 10% -10%, #d7ebe3 0%, transparent 55%),
        radial-gradient(700px 380px at 100% 0%, #e8eef2 0%, transparent 50%),
        var(--paper);
      line-height: 1.5;
    }}
    .wrap {{ max-width: 52rem; margin: 0 auto; padding: 1.5rem 1.15rem 3rem; }}
    header.hero {{
      display: grid; gap: 1.25rem;
      grid-template-columns: auto 1fr;
      align-items: center;
      margin-bottom: 1.5rem;
    }}
    @media (max-width: 640px) {{
      header.hero {{ grid-template-columns: 1fr; justify-items: start; }}
    }}
    .brand {{
      font-family: Fraunces, Georgia, serif;
      font-size: 0.85rem; letter-spacing: 0.04em;
      text-transform: uppercase; color: var(--accent); margin: 0 0 0.35rem;
    }}
    h1 {{
      font-family: Fraunces, Georgia, serif;
      font-size: clamp(1.45rem, 3vw, 1.9rem);
      margin: 0; font-weight: 700; line-height: 1.2;
    }}
    .sub {{ color: var(--muted); margin: 0.4rem 0 0; font-size: 0.95rem; }}
    .sub a {{ color: var(--accent); }}
    .ring {{
      width: 120px; height: 120px; position: relative;
    }}
    .ring svg {{ transform: rotate(-90deg); display: block; }}
    .ring .val {{
      position: absolute; inset: 0; display: grid; place-items: center;
      font-family: Fraunces, Georgia, serif; font-size: 1.85rem; font-weight: 700;
    }}
    .cta {{
      display: flex; flex-wrap: wrap; gap: 0.65rem; margin: 0.85rem 0 0;
    }}
    .cta a {{
      display: inline-block; text-decoration: none;
      background: var(--accent); color: #fff;
      padding: 0.55rem 0.95rem; border-radius: 6px; font-weight: 650;
      font-size: 0.92rem;
    }}
    .cta a.secondary {{
      background: transparent; color: var(--accent);
      border: 1px solid var(--accent);
    }}
    section {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 1rem 1.1rem 1.15rem;
      margin-bottom: 1rem;
    }}
    section h2 {{
      margin: 0 0 0.75rem;
      font-size: 1.05rem;
      font-family: Fraunces, Georgia, serif;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 0.65rem;
    }}
    @media (max-width: 640px) {{
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    .metric {{
      background: var(--paper);
      border-radius: 8px;
      padding: 0.7rem 0.75rem;
    }}
    .metric .n {{ font-size: 1.35rem; font-weight: 650; }}
    .metric .l {{ font-size: 0.78rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
    .metric.crit .n {{ color: var(--crit); }}
    .metric.warn .n {{ color: var(--warn); }}
    ul.issues, ul.recs {{ list-style: none; padding: 0; margin: 0; }}
    li.issue, ul.recs li {{
      padding: 0.65rem 0;
      border-bottom: 1px solid var(--line);
      display: grid; gap: 0.2rem;
    }}
    li.issue:last-child, ul.recs li:last-child {{ border-bottom: 0; }}
    .pill {{
      display: inline-block; font-size: 0.68rem; font-weight: 650;
      text-transform: uppercase; letter-spacing: 0.04em;
      padding: 0.15rem 0.4rem; border-radius: 4px;
      background: var(--accent-soft); color: var(--accent);
      margin-right: 0.35rem;
    }}
    .sev-critical .pill {{ background: #fde8e8; color: var(--crit); }}
    .sev-warning .pill {{ background: #fff3cd; color: var(--warn); }}
    .sev-info .pill {{ background: #e8eef6; color: var(--info); }}
    code {{ font-size: 0.82rem; background: var(--paper); padding: 0.05rem 0.3rem; border-radius: 3px; }}
    .msg {{ display: block; margin-top: 0.15rem; }}
    .url, .page {{ display: block; color: var(--muted); font-size: 0.82rem; word-break: break-all; }}
    .empty {{ color: var(--muted); margin: 0; }}
    footer {{
      margin-top: 1.25rem; color: var(--muted); font-size: 0.82rem;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="ring" aria-label="SEO score {score_label}">
        <svg width="120" height="120" viewBox="0 0 120 120" aria-hidden="true">
          <circle cx="60" cy="60" r="54" fill="none" stroke="#d5e0db" stroke-width="10" />
          <circle cx="60" cy="60" r="54" fill="none" stroke="#0f6b5c" stroke-width="10"
            stroke-linecap="round"
            stroke-dasharray="{dash:.2f} {circ:.2f}" />
        </svg>
        <div class="val">{html.escape(score_label)}</div>
      </div>
      <div>
        <p class="brand">SEO Scorecard</p>
        <h1>{seed}</h1>
        <p class="sub">Audit <code>{audit_id}</code> · {pages_n} pages · created {created}</p>
        <div class="cta">
          <a href="/share/{token_esc}?format=pdf">Download PDF</a>
          <a class="secondary" href="/share/{token_esc}?format=markdown">Markdown</a>
        </div>
      </div>
    </header>

    <section>
      <h2>At a glance</h2>
      <div class="metrics">
        <div class="metric"><div class="n">{html.escape(score_label)}</div><div class="l">Score</div></div>
        <div class="metric crit"><div class="n">{critical}</div><div class="l">Critical</div></div>
        <div class="metric warn"><div class="n">{warning}</div><div class="l">Warnings</div></div>
        <div class="metric"><div class="n">{info}</div><div class="l">Info</div></div>
      </div>
    </section>

    <section>
      <h2>Top issues</h2>
      {issues_html}
    </section>

    <section>
      <h2>Recommended next steps</h2>
      {recs_html}
    </section>

    <footer>
      Public link expires {expires}. This page is read-only advice — it does not change the live website.
    </footer>
  </div>
</body>
</html>"""
