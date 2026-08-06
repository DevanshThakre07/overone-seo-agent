"""Enforced write-scope regressions.

The previous scope-guard tests passed while the bug was live because they
called a pure function that NOTHING in the write path invoked. These tests
drive the real Hermes entry point instead — `pre_tool_call_hook` — which is the
callback that can veto a tool dispatch.

Incident being pinned: analyzing the external site actoro.app, then editing
`hermes-agent/web/index.html` (Hermes' own dashboard). The second occurrence
touched only <title> and <meta> in <head>, sidestepping a guard that looked for
injection into the #root mount point.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.write_firewall import (
    WriteBlocked,
    arm_external_scope,
    assert_write_allowed,
    confirm_site_sources,
    evaluate_tool_call,
    pre_tool_call_hook,
    release_external_scope,
)

EXTERNAL = "https://actoro.app"

# The real dashboard from the incident, if this checkout has it beside us.
HERMES_DASHBOARD = (
    Path(__file__).resolve().parents[3] / "hermes-agent" / "web" / "index.html"
)

# The edit that got through last time: head-only, mount point untouched.
HEAD_ONLY_EDIT = {
    "path": str(HERMES_DASHBOARD),
    "old_string": "<title>Hermes Agent - Dashboard</title>",
    "new_string": (
        "<title>Actoro — Active Learning & Reading App</title>\n"
        '    <meta name="description" content="Actoro is a reading app.">'
    ),
}


@pytest.fixture(autouse=True)
def _clean_scope(tmp_path_factory, monkeypatch):
    """Isolate every test from the real ~/.hermes scope state."""
    state = tmp_path_factory.mktemp("scope-state") / "write_scopes.json"
    monkeypatch.setenv("SEO_AGENT_SCOPE_STATE", str(state))
    release_external_scope()
    yield
    release_external_scope()


class TestTheExactIncident:
    @pytest.mark.skipif(
        not HERMES_DASHBOARD.exists(), reason="hermes-agent checkout not present"
    )
    def test_head_only_title_meta_edit_is_blocked(self):
        """The precise call that slipped through the mount-point guard."""
        arm_external_scope(EXTERNAL)
        result = pre_tool_call_hook(tool_name="patch", args=HEAD_ONLY_EDIT)
        assert result is not None, "head-only edit must be blocked"
        assert result["action"] == "block"
        assert "actoro.app" in result["message"]

    @pytest.mark.skipif(
        not HERMES_DASHBOARD.exists(), reason="hermes-agent checkout not present"
    )
    def test_whole_file_rewrite_is_blocked(self):
        arm_external_scope(EXTERNAL)
        result = pre_tool_call_hook(
            tool_name="write_file",
            args={"path": str(HERMES_DASHBOARD), "content": "<html>...</html>"},
        )
        assert result is not None and result["action"] == "block"

    @pytest.mark.skipif(
        not HERMES_DASHBOARD.exists(), reason="hermes-agent checkout not present"
    )
    def test_block_does_not_depend_on_edit_content(self):
        """Head, body, mount point, empty — same file, same refusal.

        This is the property the old guard lacked: it reasoned about WHAT was
        being written rather than WHICH FILE.
        """
        arm_external_scope(EXTERNAL)
        payloads = [
            {"old_string": "<title>x</title>", "new_string": "<title>y</title>"},
            {"old_string": '<div id="root">', "new_string": '<div id="root">hi'},
            {"old_string": "<body>", "new_string": "<body><h1>SEO</h1>"},
            {"old_string": "", "new_string": ""},
        ]
        for payload in payloads:
            verdict = evaluate_tool_call(
                "patch", {"path": str(HERMES_DASHBOARD), **payload}
            )
            assert verdict.blocked, payload
            assert verdict.reason_code == "unmapped_external_target"

    @pytest.mark.skipif(
        not HERMES_DASHBOARD.exists(), reason="hermes-agent checkout not present"
    )
    def test_shell_redirect_into_the_dashboard_is_blocked(self):
        arm_external_scope(EXTERNAL)
        for command in (
            f"echo '<title>Actoro</title>' > {HERMES_DASHBOARD}",
            f"sed -i '' 's/Hermes/Actoro/' {HERMES_DASHBOARD}",
            f"cp /tmp/new.html {HERMES_DASHBOARD}",
        ):
            verdict = evaluate_tool_call("terminal", {"command": command})
            assert verdict.blocked, command


class TestScopeIsAboutMappingNotFilename:
    def test_any_unmapped_html_is_blocked_while_armed(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<html><body><h1>Some site</h1></body></html>")
        arm_external_scope(EXTERNAL)
        assert evaluate_tool_call("write_file", {"path": str(page)}).blocked

    def test_confirmed_path_is_writable(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<html><body><h1>Real source</h1></body></html>")
        arm_external_scope(EXTERNAL)
        confirm_site_sources(EXTERNAL, [str(page)])
        assert not evaluate_tool_call("write_file", {"path": str(page)}).blocked

    def test_confirming_one_path_does_not_unlock_its_siblings(self, tmp_path):
        allowed = tmp_path / "index.html"
        other = tmp_path / "about.html"
        for f in (allowed, other):
            f.write_text("<html></html>")
        arm_external_scope(EXTERNAL)
        confirm_site_sources(EXTERNAL, [str(allowed)])
        assert not evaluate_tool_call("write_file", {"path": str(allowed)}).blocked
        assert evaluate_tool_call("write_file", {"path": str(other)}).blocked

    @pytest.mark.skipif(
        not HERMES_DASHBOARD.exists(), reason="hermes-agent checkout not present"
    )
    def test_agent_codebase_cannot_be_confirmed(self):
        """Confirmation is not an override for agent-owned source."""
        arm_external_scope(EXTERNAL)
        result = confirm_site_sources(EXTERNAL, [str(HERMES_DASHBOARD)])
        assert result["confirmed_paths"] == []
        assert result["refused_paths"]
        assert evaluate_tool_call(
            "patch", {"path": str(HERMES_DASHBOARD), **HEAD_ONLY_EDIT}
        ).blocked


class TestLegitimateWorkStillWorks:
    def test_nothing_is_blocked_when_no_scope_is_armed(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<html></html>")
        assert pre_tool_call_hook(tool_name="write_file", args={"path": str(page)}) is None

    def test_writing_the_audit_report_is_allowed(self, tmp_path):
        arm_external_scope(EXTERNAL)
        report = tmp_path / "actoro-seo-report.md"
        assert not evaluate_tool_call("write_file", {"path": str(report)}).blocked

    def test_report_inside_the_agent_repo_is_allowed(self):
        """Only markup is protected — the agent may still write its own docs."""
        arm_external_scope(EXTERNAL)
        from app.utils.scope_guard import seo_agent_root

        report = seo_agent_root() / "data" / "actoro-seo-report.md"
        assert not evaluate_tool_call("write_file", {"path": str(report)}).blocked

    def test_new_markup_inside_the_agent_repo_is_still_blocked(self):
        arm_external_scope(EXTERNAL)
        from app.utils.scope_guard import seo_agent_root

        page = seo_agent_root() / "web" / "landing-new.html"
        assert evaluate_tool_call("write_file", {"path": str(page)}).blocked

    def test_unrelated_source_files_are_allowed(self, tmp_path):
        arm_external_scope(EXTERNAL)
        script = tmp_path / "analysis.py"
        script.write_text("x = 1")
        assert not evaluate_tool_call("write_file", {"path": str(script)}).blocked

    def test_read_only_tools_are_never_blocked(self, tmp_path):
        arm_external_scope(EXTERNAL)
        page = tmp_path / "index.html"
        page.write_text("<html></html>")
        for tool in ("read_file", "search_files", "web_search"):
            assert not evaluate_tool_call(tool, {"path": str(page)}).blocked

    def test_harmless_shell_commands_are_allowed(self, tmp_path):
        arm_external_scope(EXTERNAL)
        for command in ("ls -la", "git status", f"cat {tmp_path}/index.html"):
            assert not evaluate_tool_call("terminal", {"command": command}).blocked


class TestBatchAndRaisingForms:
    def test_batch_edit_entries_are_inspected(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<html></html>")
        arm_external_scope(EXTERNAL)
        verdict = evaluate_tool_call(
            "multi_edit", {"edits": [{"path": str(page), "new_string": "x"}]}
        )
        assert verdict.blocked

    def test_assert_write_allowed_raises(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<html></html>")
        arm_external_scope(EXTERNAL)
        with pytest.raises(WriteBlocked):
            assert_write_allowed("write_file", {"path": str(page)})


class TestScopeSurvivesRestartAndSkippedTools:
    """Both failure modes seen in the live session.

    The model may skip the SEO tool entirely on a follow-up turn and go
    straight to write_file, and Hermes reloads plugins only at startup — so
    arming cannot live in process memory alone.
    """

    def test_scope_persists_to_disk(self):
        arm_external_scope(EXTERNAL)
        state = Path(__import__("os").environ["SEO_AGENT_SCOPE_STATE"])
        assert state.exists()
        assert "actoro.app" in state.read_text()

    def test_scope_survives_a_process_restart(self, tmp_path):
        """Simulated restart: same state file, module state re-read."""
        arm_external_scope(EXTERNAL)
        page = tmp_path / "index.html"
        page.write_text("<html></html>")

        import importlib

        import app.utils.write_firewall as wf

        importlib.reload(wf)
        assert wf.evaluate_tool_call("write_file", {"path": str(page)}).blocked

    def test_write_is_blocked_even_when_no_seo_tool_ran_this_turn(self, tmp_path):
        """The live regression: read_file -> write_file with no optimize call."""
        arm_external_scope(EXTERNAL)
        page = tmp_path / "index.html"
        page.write_text("<html></html>")
        assert evaluate_tool_call("read_file", {"path": str(page)}).blocked is False
        assert evaluate_tool_call("write_file", {"path": str(page)}).blocked

    def test_expired_scope_stops_blocking(self, tmp_path, monkeypatch):
        arm_external_scope(EXTERNAL)
        import app.utils.write_firewall as wf

        page = tmp_path / "index.html"
        page.write_text("<html></html>")
        monkeypatch.setattr(wf, "_STATE_TTL_SECONDS", -1)
        assert not wf.evaluate_tool_call("write_file", {"path": str(page)}).blocked


class TestPluginWiring:
    """The gap that let the old suite pass: the guard was never registered.

    A policy function with unit tests is not a guard. These assert the hook is
    actually handed to Hermes, which is what makes the block real.
    """

    def test_plugin_registers_the_pre_tool_call_hook(self):
        import sys

        sys.path.insert(
            0, str(Path(__file__).resolve().parents[2] / "integrations" / "hermes")
        )
        import seo_agent_plugin

        registered: dict[str, object] = {}

        class FakeCtx:
            def register_tool(self, **kwargs):
                pass

            def register_hook(self, hook_name, callback):
                registered[hook_name] = callback

        seo_agent_plugin.register(FakeCtx())
        assert "pre_tool_call" in registered, "firewall was never wired into Hermes"
        assert callable(registered["pre_tool_call"])

    def test_registered_hook_blocks_the_incident_call(self, tmp_path):
        import sys

        sys.path.insert(
            0, str(Path(__file__).resolve().parents[2] / "integrations" / "hermes")
        )
        import seo_agent_plugin

        registered: dict[str, object] = {}

        class FakeCtx:
            def register_tool(self, **kwargs):
                pass

            def register_hook(self, hook_name, callback):
                registered[hook_name] = callback

        seo_agent_plugin.register(FakeCtx())
        hook = registered["pre_tool_call"]

        page = tmp_path / "index.html"
        page.write_text("<html></html>")
        arm_external_scope(EXTERNAL)

        result = hook(tool_name="write_file", args={"path": str(page)})
        assert result is not None and result["action"] == "block"
