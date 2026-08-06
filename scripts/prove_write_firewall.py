"""End-to-end proof, through Hermes' real tool dispatcher.

Runs inside the hermes-agent venv so `model_tools.handle_function_call` is the
genuine dispatch path the LLM's tool calls travel down — not a unit-test stub.

Scenario replayed: optimize an external site (actoro.app), then attempt the
exact head-only <title>/<meta> edit to hermes-agent/web/index.html that slipped
through the mount-point guard.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERMES = Path("/Users/devanshthakre/Documents/AI-AGENT-Projects/hermes-agent")
SEO = Path("/Users/devanshthakre/Documents/AI-AGENT-Projects/SEO-Agent")
DASHBOARD = HERMES / "web" / "index.html"

sys.path.insert(0, str(HERMES))
sys.path.insert(0, str(SEO))


def digest() -> str:
    return hashlib.sha256(DASHBOARD.read_bytes()).hexdigest()


def show(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


before = digest()
print(f"dashboard: {DASHBOARD}")
print(f"sha256 before: {before}")

# Importing model_tools triggers discover_plugins(), which loads the symlinked
# seo-agent plugin and runs register(ctx) -> registers the pre_tool_call hook.
import model_tools  # noqa: E402
from hermes_cli.plugins import discover_plugins, get_plugin_manager  # noqa: E402

discover_plugins()
manager = get_plugin_manager()
hooks = getattr(manager, "_hooks", {}).get("pre_tool_call", [])

show("1. IS THE HOOK ACTUALLY REGISTERED IN HERMES?")
print(f"pre_tool_call callbacks loaded: {len(hooks)}")
for cb in hooks:
    print(f"  - {getattr(cb, '__module__', '?')}.{getattr(cb, '__name__', cb)}")
if not hooks:
    print("  !! no hook -> the firewall would be inert (this was the old bug)")

show("2. ARM THE SCOPE THE WAY A REAL SEO CALL DOES")
from app.utils.write_firewall import active_scopes, arm_external_scope  # noqa: E402

arm_external_scope("https://actoro.app")
print(f"active scopes: {[(s.host, sorted(s.confirmed_paths)) for s in active_scopes()]}")

show("3. THE INCIDENT CALL, THROUGH model_tools.handle_function_call")
incident_args = {
    "path": str(DASHBOARD),
    "old_string": "<title>Hermes Agent - Dashboard</title>",
    "new_string": (
        "<title>Actoro — Active Learning & Reading App</title>\n"
        '    <meta name="description" content="Actoro is a reading app.">'
    ),
}
print("tool: patch")
print("args:", json.dumps(incident_args, indent=2)[:400])

raw = model_tools.handle_function_call("patch", dict(incident_args), task_id="proof")
parsed = json.loads(raw)
print("\nresult:")
print(json.dumps(parsed, indent=2)[:1400])

show("4. OTHER ROUTES TO THE SAME FILE")
for tool, args in [
    ("write_file", {"path": str(DASHBOARD), "content": "<html>seo</html>"}),
    ("terminal", {"command": f"echo '<title>Actoro</title>' > {DASHBOARD}"}),
]:
    out = json.loads(model_tools.handle_function_call(tool, dict(args), task_id="proof"))
    blocked = "error" in out and "BLOCKED" in str(out.get("error", ""))
    print(f"  {tool:<12} blocked={blocked}")

show("5. DID ANY BYTE CHANGE?")
after = digest()
print(f"sha256 after : {after}")
print(f"UNCHANGED    : {before == after}")

show("6. LEGITIMATE WORK IS UNAFFECTED")
report = SEO / "data" / "_firewall_proof_report.md"
out = json.loads(
    model_tools.handle_function_call(
        "write_file",
        {"path": str(report), "content": "# report\n"},
        task_id="proof",
    )
)
wrote = report.exists()
print(f"  write report .md -> allowed={wrote}")
if wrote:
    report.unlink()

sys.exit(0 if before == after and hooks else 1)
