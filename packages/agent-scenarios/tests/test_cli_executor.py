"""CLIVendorExecutor (the real, GX10-bound adapter) degrades cleanly in-container.

No vendor CLIs exist here, so we prove the adapter (a) materializes the fixture,
(b) returns a structured error RunResult for an unconfigured vendor, and (c)
returns an error rather than raising when the configured CLI binary is absent.
This keeps the real adapter exercised (not dead code) without a live vendor.
"""

from __future__ import annotations

from pathlib import Path

from agent_scenarios import AgentScenario, CLIVendorExecutor


def _scenario() -> AgentScenario:
    return AgentScenario(
        id="s1",
        name="s1",
        task_prompt="do the thing",
        skill_under_test="plan-feature",
        vendors=["claude", "codex"],
        goal_gates={"verify": [{"id": "g", "check": "file", "path": "README.md"}]},
        fixture={"files": {"README.md": "# fixture\n"}, "git_init": True},
    )


def test_unconfigured_vendor_returns_error(tmp_path: Path) -> None:
    ex = CLIVendorExecutor(vendor_commands={"claude": "claude -p {prompt}"})
    result = ex.run(_scenario(), "codex", tmp_path / "ws")
    assert result.exit_code == 127
    assert result.error and "no CLI command configured" in result.error
    # Fixture was still materialized.
    assert (Path(result.workspace.root) / "README.md").is_file()


def test_absent_cli_binary_degrades(tmp_path: Path) -> None:
    ex = CLIVendorExecutor(vendor_commands={"claude": "definitely-not-a-real-binary-xyz {prompt}"})
    result = ex.run(_scenario(), "claude", tmp_path / "ws")
    assert result.exit_code == 127
    assert result.error and "unavailable" in result.error
