"""Enforced write scope for SEO suggestions.

Why this exists
---------------
`scope_guard` encoded the right policy but nothing ever called it: the SEO
tools do not write files, so there was no write path to guard. The only thing
standing between the host agent and the filesystem was PROSE — the
`write_policy.instruction` string and the skill markdown. An LLM routed around
that prose twice, most recently by editing only `<title>` and `<meta>` in
`hermes-agent/web/index.html` because those live in `<head>`, outside the
mount point the earlier check looked at.

The fix is to stop reasoning about the *content* of an edit entirely.

This module arms a process-wide scope lock whenever an SEO tool analyzes an
EXTERNAL url with no confirmed local source mapping. While that lock is armed,
`pre_tool_call` (a real Hermes hook that can veto dispatch) refuses any write
whose TARGET FILE is not in an explicit url -> path mapping the user supplied.
It never inspects what is being written, so "I only touched the head" is not a
loophole — it is the same blocked file.

The only way to write is `confirm_site_sources(url, paths)`, and even then a
path inside an agent/tool codebase is refused unconditionally.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.scope_guard import is_agent_codebase_path

# Scopes are persisted, not just held in memory, for two reasons learned the
# hard way:
#   1. The host agent may skip the SEO tool entirely on a follow-up turn
#      ("optimize X, now edit index.html directly") and go straight to
#      write_file. In-memory arming from an earlier turn must still apply.
#   2. Hermes loads plugins once at startup, so a restart would otherwise
#      silently disarm everything analyzed before it.
_STATE_TTL_SECONDS = 12 * 60 * 60


def _state_file() -> Path:
    override = os.environ.get("SEO_AGENT_SCOPE_STATE")
    if override:
        return Path(override)
    return Path.home() / ".hermes" / "seo-agent" / "write_scopes.json"

# Host-agent tools that can mutate a file. Deliberately broader than the tools
# Hermes ships today so a renamed or newly added writer is covered by default.
_WRITE_TOOL_PATH_ARGS: dict[str, tuple[str, ...]] = {
    "write_file": ("path", "file_path", "filename"),
    "patch": ("path", "file_path"),
    "edit_file": ("path", "file_path", "target_file"),
    "create_file": ("path", "file_path"),
    "apply_patch": ("path", "file_path"),
    "multi_edit": ("path", "file_path"),
    "str_replace": ("path", "file_path"),
    "str_replace_editor": ("path", "file_path"),
    "notebook_edit": ("path", "target_notebook"),
    "delete_file": ("path", "file_path"),
}

# Shell-ish tools: the command string is scanned for write verbs.
_SHELL_TOOLS = frozenset(
    {"terminal", "shell", "bash", "sh", "shell_exec", "run_command", "execute_code"}
)

# Markup/template files are what an "apply my SEO copy" edit lands in.
_WEB_SOURCE_SUFFIXES = frozenset(
    {
        ".html", ".htm", ".xhtml", ".shtml",
        ".jsx", ".tsx", ".vue", ".svelte", ".astro",
        ".php", ".erb", ".twig", ".njk", ".hbs", ".ejs", ".liquid",
        ".mustache", ".jinja", ".jinja2", ".j2", ".haml", ".slim",
        ".pug", ".jade", ".blade",
    }
)

# Redirections and in-place editors used to mutate a file from a shell.
_SHELL_WRITE_PATTERNS = (
    r">>?\s*\S",
    r"\bsed\b[^|;]*-i",
    r"\bperl\b[^|;]*-i",
    r"\btee\b",
    r"\b(cp|mv|rsync|install|truncate|dd|ex|patch)\b",
    r"""\bopen\s*\([^)]*['"][wa]""",
)


class WriteBlocked(Exception):
    """Raised by :func:`assert_write_allowed` when a write is out of scope."""


@dataclass
class ExternalScope:
    """An armed lock for one external target host."""

    host: str
    url: str
    confirmed_paths: set[str] = field(default_factory=set)
    armed_at: float = field(default_factory=time.time)

    def permits(self, resolved: str) -> bool:
        return resolved in self.confirmed_paths

    def expired(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.armed_at > _STATE_TTL_SECONDS

    def to_json(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "url": self.url,
            "confirmed_paths": sorted(self.confirmed_paths),
            "armed_at": self.armed_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ExternalScope":
        return cls(
            host=data["host"],
            url=data.get("url", data["host"]),
            confirmed_paths=set(data.get("confirmed_paths") or []),
            armed_at=float(data.get("armed_at") or time.time()),
        )


@dataclass
class Verdict:
    blocked: bool
    message: str | None = None
    tool_name: str = ""
    path: str | None = None
    reason_code: str = ""

    def as_hook_result(self) -> dict[str, Any] | None:
        if not self.blocked:
            return None
        return {"action": "block", "message": self.message}


_lock = threading.RLock()

# In-process mirror of the persisted scopes. Disk adds restart survival, but if
# the state directory is unwritable (sandbox, read-only home, permissions) the
# guard must still hold for this process rather than failing open.
_memory: dict[str, ExternalScope] = {}


def _read_disk_state() -> dict[str, ExternalScope]:
    path = _state_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = time.time()
    scopes: dict[str, ExternalScope] = {}
    for entry in raw.get("scopes", []):
        try:
            scope = ExternalScope.from_json(entry)
        except (KeyError, TypeError, ValueError):
            continue
        if not scope.expired(now):
            scopes[scope.host] = scope
    return scopes


def _read_state() -> dict[str, ExternalScope]:
    """Disk state merged over the in-process mirror, newest arming wins."""
    now = time.time()
    merged: dict[str, ExternalScope] = {
        host: scope for host, scope in _memory.items() if not scope.expired(now)
    }
    for host, scope in _read_disk_state().items():
        existing = merged.get(host)
        if existing is None:
            merged[host] = scope
        else:
            existing.confirmed_paths |= scope.confirmed_paths
            existing.armed_at = max(existing.armed_at, scope.armed_at)
    return merged


def _write_state(scopes: dict[str, ExternalScope]) -> None:
    """Mirror in memory first (always works), then try to persist."""
    global _memory
    _memory = dict(scopes)

    path = _state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"scopes": [s.to_json() for s in scopes.values()]}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        # Restart survival is lost, but the in-memory mirror still guards
        # this process. Never fail open, and never break the tool.
        pass


# ---------------------------------------------------------------- scope state


def _host_of(url: str) -> str:
    parsed = urlparse(url if "//" in url else f"//{url}")
    return (parsed.netloc or url).lower().removeprefix("www.")


def _resolve(path: str | Path) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return str(path)


def arm_external_scope(url: str) -> ExternalScope:
    """Lock down writes for an external target. Called by every SEO tool."""
    host = _host_of(url)
    with _lock:
        scopes = _read_state()
        scope = scopes.get(host)
        if scope is None:
            scope = ExternalScope(host=host, url=url)
            scopes[host] = scope
        else:
            scope.armed_at = time.time()
        _write_state(scopes)
        return scope


def confirm_site_sources(url: str, paths: list[str]) -> dict[str, Any]:
    """Record an explicit url -> local path mapping.

    This is the ONLY way a write becomes permitted. Agent/tool source is
    refused here so a confirmation can never authorize editing the dashboard.
    """
    host = _host_of(url)
    accepted: list[str] = []
    refused: list[dict[str, str]] = []

    for raw in paths:
        resolved = _resolve(raw)
        is_agent, reason = is_agent_codebase_path(resolved)
        if is_agent:
            refused.append({"path": resolved, "reason": reason or "agent codebase"})
            continue
        accepted.append(resolved)

    with _lock:
        scopes = _read_state()
        scope = scopes.get(host) or ExternalScope(host=host, url=url)
        scope.confirmed_paths.update(accepted)
        scopes[host] = scope
        _write_state(scopes)

    return {
        "host": host,
        "confirmed_paths": sorted(scope.confirmed_paths),
        "refused_paths": refused,
        "note": (
            f"{len(accepted)} path(s) mapped to {host}. Only these may be edited. "
            "Paths inside an agent/tool codebase are never accepted."
        ),
    }


def release_external_scope(url: str | None = None) -> None:
    """Drop the lock. Used by tests and by an explicit user reset."""
    with _lock:
        if url is None:
            _write_state({})
            return
        scopes = _read_state()
        scopes.pop(_host_of(url), None)
        _write_state(scopes)


def active_scopes() -> list[ExternalScope]:
    """Armed scopes, reloaded from disk so a restart cannot disarm the guard."""
    with _lock:
        return list(_read_state().values())


# ------------------------------------------------------------------ decision


def _candidate_paths(tool_name: str, args: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in _WRITE_TOOL_PATH_ARGS.get(tool_name, ()):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value)
    # Batch editors take a list of {path: ...} entries.
    for key in ("edits", "files", "operations"):
        value = args.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    for sub in ("path", "file_path", "target_file"):
                        if isinstance(entry.get(sub), str):
                            paths.append(entry[sub])
    return paths


def _shell_targets(command: str) -> list[str]:
    """Path-looking tokens in a command that appears to mutate something."""
    if not any(re.search(p, command) for p in _SHELL_WRITE_PATTERNS):
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return [
        t
        for t in tokens
        if ("/" in t or Path(t).suffix) and not t.startswith("-")
    ]


def _is_protected_target(resolved: str) -> tuple[bool, str]:
    """Would writing here plausibly be 'applying SEO copy to a site'?

    Only markup/template files qualify, so ordinary work — writing an audit
    report, scratch files, Python — is never touched. Inside an agent/tool
    codebase the file need not already exist, since creating a new page there
    is just as wrong as editing one.
    """
    path = Path(resolved)
    if path.suffix.lower() not in _WEB_SOURCE_SUFFIXES:
        return False, ""

    is_agent, reason = is_agent_codebase_path(resolved)
    if is_agent:
        return True, reason or "path is inside an agent/tool codebase"
    if path.exists():
        return True, f"{path.name} is an existing markup/template file"
    return False, ""


def evaluate_tool_call(tool_name: str, args: dict[str, Any] | None) -> Verdict:
    """Decide whether a host-agent tool call may proceed.

    Content is never examined — only which file is being written. An edit
    confined to <head> is therefore treated exactly like any other edit to
    that file.
    """
    scopes = active_scopes()
    if not scopes:
        return Verdict(blocked=False, tool_name=tool_name)

    args = args or {}
    if tool_name in _SHELL_TOOLS:
        command = args.get("command") or args.get("cmd") or ""
        targets = _shell_targets(command) if isinstance(command, str) else []
    elif tool_name in _WRITE_TOOL_PATH_ARGS:
        targets = _candidate_paths(tool_name, args)
    else:
        return Verdict(blocked=False, tool_name=tool_name)

    for raw in targets:
        resolved = _resolve(raw)
        protected, why = _is_protected_target(resolved)
        if not protected:
            continue
        if any(scope.permits(resolved) for scope in scopes):
            continue

        hosts = ", ".join(sorted(s.host for s in scopes))
        message = (
            f"BLOCKED by seo-agent write firewall: refusing `{tool_name}` on "
            f"{resolved}.\n\n"
            f"An SEO analysis is active for the EXTERNAL site(s): {hosts}. "
            f"This machine has no confirmed mapping between {hosts} and that "
            f"file ({why}), so it cannot be that site's source.\n\n"
            "SEO results are copy RECOMMENDATIONS for a human to apply on the "
            "live site. They are never applied by editing local files that "
            "merely look site-like.\n\n"
            "This block is about WHICH FILE, not which part of it — editing "
            "only <title>/<meta>, or any other subset, is blocked identically.\n\n"
            "If local source for this site really does exist here, ask the user "
            "to name the exact files, then call "
            f"confirm_site_sources(url='{scopes[0].url}', paths=[...]). "
            "Files inside an agent/tool codebase are never accepted."
        )
        return Verdict(
            blocked=True,
            message=message,
            tool_name=tool_name,
            path=resolved,
            reason_code="unmapped_external_target",
        )

    return Verdict(blocked=False, tool_name=tool_name)


def pre_tool_call_hook(
    tool_name: str = "", args: dict[str, Any] | None = None, **_kwargs: Any
) -> dict[str, Any] | None:
    """Hermes ``pre_tool_call`` callback. Returning a block dict vetoes dispatch."""
    return evaluate_tool_call(tool_name, args).as_hook_result()


def assert_write_allowed(tool_name: str, args: dict[str, Any] | None) -> None:
    """Raising form, for any in-process write path we add later."""
    verdict = evaluate_tool_call(tool_name, args)
    if verdict.blocked:
        raise WriteBlocked(verdict.message or "write blocked")
