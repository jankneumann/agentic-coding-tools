"""Tests for ``vendor_health.py``, the probe the coordinator watchdog persists.

A crash in ``check_vendor`` aborts ``check_all_vendors`` for every lane, so a
single malformed agent entry leaves the whole vendor registry unprobed (#643).
"""

from __future__ import annotations

import vendor_health


def test_present_but_null_cli_section_does_not_crash() -> None:
    # /agents/dispatch-configs serializes an agent without a CLI as "cli": null;
    # .get("cli", {}) only defaults a *missing* key, not a null one.
    health = vendor_health.check_vendor(
        "codex-remote", {"type": "codex", "cli": None, "sdk": {"api_key_env": "UNSET_FOR_TEST"}}
    )

    assert health.agent_id == "codex-remote"
    assert health.cli_command == ""
    assert health.cli_installed is False


def test_one_null_cli_lane_does_not_hide_the_others(monkeypatch) -> None:
    monkeypatch.setattr(
        vendor_health,
        "load_agents_yaml",
        lambda _path=None: {
            "agents": {
                "codex-remote": {"type": "codex", "cli": None},
                "claude-local": {"type": "claude_code", "cli": {"command": "true"}},
            }
        },
    )

    report = vendor_health.check_all_vendors()

    assert [v.agent_id for v in report.vendors] == ["codex-remote", "claude-local"]
