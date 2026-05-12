"""CLI integration tests for `skills/autopilot/scripts/runner.py`.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
      Requirement: Sub-Agent Dispatch Protocol Helpers
      Scenario: build_phase_dispatch_kwargs returns dispatch-ready dict
Design decisions: D3 (CLI surface).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


_RUNNER = Path(__file__).resolve().parents[2] / "autopilot" / "scripts" / "runner.py"


def _seed_state(repo_root: Path, change_id: str, **overrides: Any) -> Path:
    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schema_version": 3,
        "change_id": change_id,
        "current_phase": "IMPLEMENT",
        "iteration": 0,
        "total_iterations": 0,
        "max_phase_iterations": 3,
        "findings_trend": [],
        "blocking_findings": [],
        "vendor_availability": {},
        "packages_status": {},
        "package_authors": {},
        "implementation_strategy": {},
        "memory_ids": [],
        "handoff_ids": [],
        "last_handoff_id": None,
        "started_at": "2026-05-05T00:00:00+00:00",
        "phase_started_at": "2026-05-05T00:00:00+00:00",
        "previous_phase": None,
        "escalation_reason": None,
        "val_review_enabled": False,
        "cli_review_enabled": True,
        "error": None,
        "phase_archetype": None,
    }
    state.update(overrides)
    state_path = change_dir / "loop-state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    return state_path


def _run_cli(cwd: Path, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    import os
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    # Make sibling skill scripts importable inside the subprocess (mirrors
    # conftest.py's sys.path injection for in-process tests).
    extra_path = ":".join(
        str(_RUNNER.parents[2] / sub) for sub in (
            "autopilot/scripts", "coordination-bridge/scripts", "session-log/scripts",
        )
    )
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = extra_path + (":" + existing if existing else "")
    return subprocess.run(
        [sys.executable, str(_RUNNER), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def test_runner_build_dispatch_emits_json(workspace: Path) -> None:
    _seed_state(workspace, "demo")

    # Force the bridge into "no coordinator" mode — null model/system_prompt.
    result = _run_cli(
        workspace, "build-dispatch", "--phase", "IMPLEMENT", "--change-id", "demo",
        env_extra={
            "COORDINATION_API_URL": "",  # disable bridge
            "AUTOPILOT_PHASE_MODEL_OVERRIDE": "",
        },
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout.strip())
    assert set(payload.keys()) >= {"prompt", "model", "system_prompt", "isolation", "archetype"}
    # IMPLEMENT phase enforces worktree isolation regardless of bridge.
    assert payload["isolation"] == "worktree"
    # No bridge → no model/system_prompt.
    assert payload["model"] is None
    assert payload["system_prompt"] is None
    assert payload["archetype"] is None


def test_runner_apply_outcome_updates_state(workspace: Path) -> None:
    state_path = _seed_state(workspace, "demo")
    # Pre-write a valid cache so apply-outcome propagates the archetype.
    cache = workspace / "openspec" / "changes" / "demo" / ".phase-resolution-cache.json"
    archetype = "implementer"
    checksum = hashlib.sha256(
        b"demo" + b"IMPLEMENT" + archetype.encode("utf-8")
    ).hexdigest()
    cache.write_text(json.dumps({
        "schema_version": 1,
        "change_id": "demo",
        "phase": "IMPLEMENT",
        "archetype": archetype,
        "checksum": checksum,
    }))

    result = _run_cli(
        workspace, "apply-outcome",
        "--change-id", "demo", "--phase", "IMPLEMENT",
        "--outcome", "continue", "--handoff-id", "h-cli",
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    state = json.loads(state_path.read_text())
    assert state["last_handoff_id"] == "h-cli"
    assert state["phase_archetype"] == "implementer"
    # Cache deleted.
    assert not cache.exists()


def test_runner_rejects_traversal_change_id(workspace: Path) -> None:
    result = _run_cli(
        workspace, "build-dispatch", "--phase", "IMPLEMENT",
        "--change-id", "../../etc/passwd",
    )
    assert result.returncode != 0
    assert "invalid change_id" in (result.stderr + result.stdout)


def test_runner_help_lists_subcommands(workspace: Path) -> None:
    result = _run_cli(workspace, "--help")
    assert result.returncode == 0
    assert "build-dispatch" in result.stdout
    assert "apply-outcome" in result.stdout
