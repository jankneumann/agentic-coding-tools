"""Tests for lifecycle hook installer output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_HOOKS = REPO_ROOT / "agent-coordinator" / "scripts" / "install_hooks.py"
SCRIPTS_DIR = REPO_ROOT / "agent-coordinator" / "scripts"
MAKEFILE = REPO_ROOT / "agent-coordinator" / "Makefile"


def run_installer(tmp_path: Path, *args: str) -> Path:
    target = tmp_path / "settings.json"
    subprocess.run(
        [
            sys.executable,
            str(INSTALL_HOOKS),
            "--scripts-dir",
            str(SCRIPTS_DIR),
            "--target",
            str(target),
            "--coordination-api-url",
            "http://localhost:8081",
            *args,
        ],
        check=True,
    )
    return target


def test_codex_hooks_use_codex_identity_and_supported_events(tmp_path: Path) -> None:
    target = run_installer(
        tmp_path,
        "--agent",
        "codex",
        "--agent-id",
        "codex-local",
        "--agent-type",
        "codex",
    )

    hooks = json.loads(target.read_text())["hooks"]

    assert set(hooks) == {"SessionStart", "Stop"}
    commands = [
        hook["command"]
        for hook_group in hooks.values()
        for hook in hook_group
    ]
    assert all('AGENT_ID="${AGENT_ID:-codex-local}"' in command for command in commands)
    assert all('AGENT_TYPE="${AGENT_TYPE:-codex}"' in command for command in commands)
    assert all("COORDINATION_API_URL=" in command for command in commands)
    assert not any("deregister_agent.py" in command for command in commands)


def test_claude_hooks_keep_claude_settings_shape_and_session_end(tmp_path: Path) -> None:
    target = run_installer(
        tmp_path,
        "--agent",
        "claude",
        "--agent-id",
        "claude-local",
        "--agent-type",
        "claude_code",
    )

    settings = json.loads(target.read_text())
    hooks = settings["hooks"]

    assert set(hooks) == {"SessionStart", "Stop", "SubagentStop", "SessionEnd"}
    assert all(
        "matcher" in group and "hooks" in group
        for groups in hooks.values()
        for group in groups
    )

    session_end_commands = [
        hook["command"]
        for group in hooks["SessionEnd"]
        for hook in group["hooks"]
    ]
    assert any("deregister_agent.py" in command for command in session_end_commands)


def test_makefile_wires_codex_to_hooks_json_and_codex_identity() -> None:
    makefile = MAKEFILE.read_text()

    assert 'CODEX_AGENT_ID    ?= codex-1' in makefile
    assert 'CODEX_AGENT_TYPE  ?= codex' in makefile
    assert '--target "$(HOME)/.codex/hooks.json"' in makefile
    assert '--agent-id "$(CODEX_AGENT_ID)"' in makefile
    assert '--agent-type "$(CODEX_AGENT_TYPE)"' in makefile
    assert '--target "$(HOME)/.codex/settings.json"' not in makefile
