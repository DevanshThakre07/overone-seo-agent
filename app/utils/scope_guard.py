"""Scope boundaries for SEO suggestions.

Background: a host agent took the concrete rewrite copy returned by
`optimize_page` / `keyword_plan` for the external site actoro.app and applied it
to `hermes-agent/web/index.html` — the agent's OWN dashboard — because that file
was the nearest thing named `index.html`. The SEO tools never write files, but
their output looked like "here is the HTML to install", with nothing stating
where it may legitimately be applied.

This module makes the boundary explicit and machine-checkable:

* `build_write_policy()` — the recommendations-only contract shipped with every
  optimization response.
* `evaluate_local_target()` — refuses a local file as the target of an external
  URL's suggestions, and refuses framework mount points outright.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Directories/files that identify a tree as agent/tool source rather than a
# user's website. Checked against every ancestor of a candidate path.
_AGENT_MARKER_DIRS = (
    "hermes_cli",
    "seo_agent_plugin",
    "ui-tui",
    "hermes_ink",
)
_AGENT_MARKER_PROJECT_NAMES = ("seo-agent", "hermes-agent", "hermes_cli")

# Runtime mount points. Static content injected here is wiped on hydration, so
# an "SEO fix" placed inside them is worse than useless.
_MOUNT_POINT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"""<div[^>]*\bid=["']root["']""", "React/Vite mount point (#root)"),
    (r"""<div[^>]*\bid=["']app["']""", "Vue/Vite mount point (#app)"),
    (r"""<div[^>]*\bid=["']__next["']""", "Next.js mount point (#__next)"),
    (r"""<div[^>]*\bid=["']__nuxt["']""", "Nuxt mount point (#__nuxt)"),
    (r"""<div[^>]*\bid=["']___gatsby["']""", "Gatsby mount point (#___gatsby)"),
    (r"""<div[^>]*\bid=["']svelte["']""", "Svelte mount point (#svelte)"),
    (r"""<div[^>]*\bdata-reactroot""", "React server-rendered root"),
    (r"""<app-root""", "Angular mount point (<app-root>)"),
    (r"""\bng-app=""", "AngularJS mount point (ng-app)"),
)

_SEO_AGENT_ROOT = Path(__file__).resolve().parents[2]


class ScopeViolation(Exception):
    """Raised when a write would cross out of the user's site into agent code."""


def seo_agent_root() -> Path:
    return _SEO_AGENT_ROOT


def is_agent_codebase_path(path: str | Path) -> tuple[bool, str | None]:
    """Is this path inside the agent's/tool's own source tree?

    Returns (is_agent_code, reason).
    """
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False, None

    if resolved == _SEO_AGENT_ROOT or _SEO_AGENT_ROOT in resolved.parents:
        return True, f"path is inside the SEO-Agent tool source tree ({_SEO_AGENT_ROOT.name})"

    for ancestor in (resolved, *resolved.parents):
        for marker in _AGENT_MARKER_DIRS:
            if (ancestor / marker).exists():
                return True, f"ancestor {ancestor.name}/ contains agent source marker '{marker}/'"
        pyproject = ancestor / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            for name in _AGENT_MARKER_PROJECT_NAMES:
                if name in text:
                    return True, (
                        f"ancestor {ancestor.name}/ is the '{name}' project "
                        "(agent/tool source, not a user website)"
                    )
    return False, None


def detect_mount_points(html: str | None) -> list[dict[str, str]]:
    """Framework mount points found in markup — never inject content into these."""
    found: list[dict[str, str]] = []
    for pattern, label in _MOUNT_POINT_PATTERNS:
        match = re.search(pattern, html or "", re.IGNORECASE)
        if match:
            found.append({"match": match.group(0)[:80], "description": label})
    return found


def build_write_policy(
    target_url: str,
    *,
    confirmed_local_paths: list[str] | None = None,
) -> dict[str, Any]:
    """The contract that ships with every set of copy suggestions."""
    host = urlparse(target_url).netloc or target_url
    if confirmed_local_paths:
        return {
            "may_write_files": True,
            "mode": "user_confirmed_local_source",
            "confirmed_paths": confirmed_local_paths,
            "instruction": (
                f"The user explicitly identified these files as the source of {host}. "
                "Only these paths may be edited. Never inject content into a framework "
                "mount point; edit the component/template that renders it instead."
            ),
        }
    return {
        "may_write_files": False,
        "mode": "recommendations_only",
        "target_host": host,
        "instruction": (
            f"{host} is an EXTERNAL, separately-hosted website. Its source code is NOT "
            "on this machine. These are copy RECOMMENDATIONS for a human to apply on "
            "that site. Do NOT create, edit, or patch any local file in response to "
            "this result — in particular do not guess that a local index.html, "
            "template, or dashboard file represents this site. If the user wants local "
            "files changed, ask them which exact files correspond to this site first."
        ),
        "forbidden_actions": [
            "editing any local file to 'apply' these suggestions",
            "searching the workspace for the site's markup",
            "treating any local index.html as this site's source",
            "injecting content into a framework mount point (#root, #app, #__next, ...)",
        ],
    }


def _is_mapped(target_url: str, path: Path) -> bool:
    """Was this exact path registered as source for this host by the user?"""
    try:
        from app.utils.write_firewall import active_scopes

        resolved = str(path.expanduser().resolve())
    except Exception:  # noqa: BLE001
        return False
    host = (urlparse(target_url).netloc or target_url).lower().removeprefix("www.")
    return any(
        scope.host == host and scope.permits(resolved) for scope in active_scopes()
    )


def evaluate_local_target(
    target_url: str,
    candidate_path: str | Path,
    *,
    html: str | None = None,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    """Decide whether `candidate_path` may receive suggestions for `target_url`.

    Refuses agent-owned source unconditionally, unconfirmed guesses by default,
    and any file whose content is a framework mount point shell.
    """
    path = Path(candidate_path)
    host = urlparse(target_url).netloc or target_url
    verdict: dict[str, Any] = {
        "allowed": False,
        "target_url": target_url,
        "candidate_path": str(path),
        "reasons": [],
        "clarifying_question": None,
    }

    is_agent, agent_reason = is_agent_codebase_path(path)
    if is_agent:
        verdict["reasons"].append(
            f"REFUSED: {agent_reason}. Editing the agent's own codebase in response to a "
            f"request about {host} is never correct."
        )
        verdict["clarifying_question"] = (
            f"This file belongs to the tooling, not to {host}. Which file(s) actually "
            f"contain {host}'s source, if any are on this machine?"
        )
        return verdict

    if not user_confirmed:
        verdict["reasons"].append(
            f"REFUSED: no confirmation that {path.name} is part of {host}. File names such "
            "as index.html are not evidence of ownership."
        )
        verdict["clarifying_question"] = (
            f"Do you want me to edit {path}? Please confirm it is {host}'s source."
        )
        return verdict

    # A bare "yes" is not a url -> path mapping. Confirmation only counts when
    # this exact path was registered against this host via
    # write_firewall.confirm_site_sources(). Without that, `user_confirmed=True`
    # is just the model asserting its own guess was approved.
    if not _is_mapped(target_url, path):
        verdict["reasons"].append(
            f"REFUSED: {path} has never been mapped to {host}. A boolean confirmation "
            "is not a mapping — the user must name this exact file via "
            "confirm_site_sources() before it can be written."
        )
        verdict["clarifying_question"] = (
            f"Which exact local files hold {host}'s source? I will not infer them."
        )
        return verdict

    if html is not None:
        mounts = detect_mount_points(html)
        if mounts:
            verdict["mount_points"] = mounts
            verdict["reasons"].append(
                "REFUSED: file contains "
                + ", ".join(m["description"] for m in mounts)
                + ". Content placed inside a mount point is replaced at runtime and can "
                "cause a hydration mismatch. Edit the component/template that renders "
                "this markup instead."
            )
            return verdict

    verdict["allowed"] = True
    verdict["reasons"].append(f"User confirmed {path} is source for {host}.")
    return verdict


def assert_safe_local_write(
    target_url: str,
    candidate_path: str | Path,
    *,
    html: str | None = None,
    user_confirmed: bool = False,
) -> None:
    """Hard guard for any future write path. Raises instead of proceeding."""
    verdict = evaluate_local_target(
        target_url, candidate_path, html=html, user_confirmed=user_confirmed
    )
    if not verdict["allowed"]:
        raise ScopeViolation(" ".join(verdict["reasons"]))
