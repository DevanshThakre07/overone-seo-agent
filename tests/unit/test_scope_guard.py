"""Scope-boundary regressions.

Reproduces the incident where suggestions for the external site actoro.app were
written into the agent's own dashboard at hermes-agent/web/index.html.
"""

from __future__ import annotations

import pytest

from app.utils.scope_guard import (
    ScopeViolation,
    assert_safe_local_write,
    build_write_policy,
    detect_mount_points,
    evaluate_local_target,
    is_agent_codebase_path,
    seo_agent_root,
)
from app.utils.write_firewall import confirm_site_sources, release_external_scope

VITE_SHELL = """<!doctype html>
<html><head><title>Hermes Agent - Dashboard</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>
"""


@pytest.fixture(autouse=True)
def _isolate_scope_state(tmp_path_factory, monkeypatch):
    """Keep these tests off the real ~/.hermes scope state."""
    state = tmp_path_factory.mktemp("scope-state") / "write_scopes.json"
    monkeypatch.setenv("SEO_AGENT_SCOPE_STATE", str(state))
    release_external_scope()
    yield
    release_external_scope()


class TestAgentCodebaseDetection:
    def test_seo_agent_own_source_is_agent_code(self):
        is_agent, reason = is_agent_codebase_path(seo_agent_root() / "app" / "main.py")
        assert is_agent is True
        assert reason

    def test_seo_agent_plugin_dir_is_agent_code(self):
        path = seo_agent_root() / "integrations" / "hermes" / "seo_agent_plugin"
        assert is_agent_codebase_path(path)[0] is True

    def test_unrelated_temp_path_is_not_agent_code(self, tmp_path):
        assert is_agent_codebase_path(tmp_path / "site" / "index.html")[0] is False


class TestExternalUrlNeverWritesLocalFiles:
    def test_policy_forbids_writes_for_external_site(self):
        policy = build_write_policy("https://actoro.app")
        assert policy["may_write_files"] is False
        assert policy["mode"] == "recommendations_only"
        assert "EXTERNAL" in policy["instruction"]
        assert any("index.html" in a for a in policy["forbidden_actions"])

    def test_policy_allows_only_confirmed_paths(self):
        policy = build_write_policy(
            "https://actoro.app", confirmed_local_paths=["/srv/actoro/index.html"]
        )
        assert policy["may_write_files"] is True
        assert policy["confirmed_paths"] == ["/srv/actoro/index.html"]

    def test_agent_dashboard_is_refused_even_if_user_confirms(self):
        """The incident path: refusing agent source is not overridable."""
        verdict = evaluate_local_target(
            "https://actoro.app",
            seo_agent_root() / "web" / "index.html",
            html=VITE_SHELL,
            user_confirmed=True,
        )
        assert verdict["allowed"] is False
        assert "REFUSED" in verdict["reasons"][0]
        assert verdict["clarifying_question"]

    def test_unconfirmed_local_file_is_refused_and_asks(self, tmp_path):
        target = tmp_path / "index.html"
        target.write_text("<html><body><p>hi</p></body></html>")
        verdict = evaluate_local_target("https://actoro.app", target)
        assert verdict["allowed"] is False
        assert "not evidence of ownership" in verdict["reasons"][0]
        assert "confirm" in verdict["clarifying_question"].lower()

    def test_bare_confirmation_without_a_mapping_is_refused(self, tmp_path):
        """`user_confirmed=True` alone is the model asserting its own guess."""
        target = tmp_path / "site.html"
        target.write_text("<html><body><h1>Real content</h1></body></html>")
        verdict = evaluate_local_target(
            "https://actoro.app",
            target,
            html=target.read_text(),
            user_confirmed=True,
        )
        assert verdict["allowed"] is False
        assert "not a mapping" in verdict["reasons"][0]

    def test_mapped_and_confirmed_file_is_allowed(self, tmp_path):
        target = tmp_path / "site.html"
        target.write_text("<html><body><h1>Real content</h1></body></html>")
        confirm_site_sources("https://actoro.app", [str(target)])
        try:
            verdict = evaluate_local_target(
                "https://actoro.app",
                target,
                html=target.read_text(),
                user_confirmed=True,
            )
        finally:
            release_external_scope()
        assert verdict["allowed"] is True


class TestMountPointProtection:
    def test_react_root_is_detected(self):
        mounts = detect_mount_points(VITE_SHELL)
        assert mounts
        assert "React/Vite" in mounts[0]["description"]

    @pytest.mark.parametrize(
        "markup",
        [
            '<div id="app"></div>',
            '<div id="__next"></div>',
            '<div id="__nuxt"></div>',
            "<app-root></app-root>",
            '<div ng-app="x"></div>',
        ],
    )
    def test_other_frameworks_are_detected(self, markup):
        assert detect_mount_points(markup)

    def test_plain_html_has_no_mount_points(self):
        assert detect_mount_points("<html><body><h1>Hello</h1></body></html>") == []

    def test_mapped_file_still_refused_if_it_is_a_mount_shell(self, tmp_path):
        """Mount-point refusal survives a legitimate url -> path mapping."""
        target = tmp_path / "index.html"
        target.write_text(VITE_SHELL)
        confirm_site_sources("https://actoro.app", [str(target)])
        try:
            verdict = evaluate_local_target(
                "https://actoro.app", target, html=VITE_SHELL, user_confirmed=True
            )
        finally:
            release_external_scope()
        assert verdict["allowed"] is False
        assert "hydration mismatch" in verdict["reasons"][0]


class TestHardGuard:
    def test_assert_raises_for_agent_path(self):
        with pytest.raises(ScopeViolation):
            assert_safe_local_write(
                "https://actoro.app",
                seo_agent_root() / "web" / "index.html",
                user_confirmed=True,
            )

    def test_assert_raises_for_unconfirmed_path(self, tmp_path):
        with pytest.raises(ScopeViolation):
            assert_safe_local_write("https://actoro.app", tmp_path / "index.html")
