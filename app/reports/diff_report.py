from __future__ import annotations

from app.models.diff import AuditDiff


def render_diff_markdown(diff: AuditDiff) -> str:
    lines = [
        "# SEO Audit Change Report",
        "",
        f"**URL:** {diff.url}",
        f"**Current audit:** {diff.current_audit_id}",
        f"**Previous audit:** {diff.previous_audit_id or 'None'}",
        f"**Current score:** {diff.current_score:.1f}/100",
    ]
    if diff.previous_score is not None:
        lines.append(f"**Previous score:** {diff.previous_score:.1f}/100")
    lines.append(f"**Score delta:** {diff.score_delta:+.1f}")
    lines.extend(["", "## Summary", "", diff.summary or "No changes summarized.", ""])

    lines.extend(["## New Issues", ""])
    if diff.new_issues:
        lines.extend(
            [
                f"- [{i.code}] {i.message}" + (f" (`{i.url}`)" if i.url else "")
                for i in diff.new_issues
            ]
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Resolved Issues", ""])
    if diff.resolved_issues:
        lines.extend(
            [
                f"- [{i.code}] {i.message}" + (f" (`{i.url}`)" if i.url else "")
                for i in diff.resolved_issues
            ]
        )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Unchanged",
            "",
            f"- {diff.unchanged_issue_count} issue(s) still present",
            "",
        ]
    )
    return "\n".join(lines)


def render_diff_json(diff: AuditDiff) -> str:
    return diff.model_dump_json(indent=2)
