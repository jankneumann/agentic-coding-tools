"""Layer B + C tests: dispatch prompts forbid sub-agent state mutation.

Spec: openspec/changes/fix-autopilot-archetype-and-apply-outcome/specs/
      skill-workflow/spec.md
      Requirement: "Sub-Agent Dispatch Prompts Forbid State Mutation by Two Paths"

Every write-capable phase's rendered prompt must instruct the sub-agent to
return (outcome, handoff_id) only and forbid BOTH (B) running
`runner.py apply-outcome` and (C) editing loop-state.json directly. Read-only /
state-only phases are exempt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import coordination_bridge
import phase_agent
import pytest

_WRITE_CAPABLE_PHASES = [
    "PLAN", "PLAN_ITERATE", "PLAN_REVIEW", "PLAN_FIX",
    "IMPLEMENT", "IMPL_ITERATE", "IMPL_REVIEW", "IMPL_FIX",
    "VALIDATE", "VAL_REVIEW", "VAL_FIX",
]


@pytest.fixture(autouse=True)
def _stub_bridge_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPILOT_PHASE_MODEL_OVERRIDE", raising=False)
    # No coordinator: archetype resolves to None so the prompt is the bare
    # scaffold (the prohibitions are appended regardless of archetype).
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **kwargs: None,
    )


def _seed(repo_root: Path, phase: str) -> None:
    change_dir = repo_root / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "loop-state.json").write_text(
        json.dumps({
            "schema_version": 4, "change_id": "demo",
            "current_phase": phase, "handoff_ids": [], "last_handoff_id": None,
        })
    )


@pytest.fixture()
def chdir_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _render(phase: str) -> str:
    return phase_agent.build_phase_dispatch_kwargs(phase, "demo")["prompt"]


@pytest.mark.parametrize("phase", _WRITE_CAPABLE_PHASES)
def test_write_capable_phase_has_layer_b_and_c(chdir_tmp: Path, phase: str) -> None:
    _seed(chdir_tmp, phase)
    prompt = _render(phase)
    # Layer B — subcommand prohibition.
    assert "apply-outcome" in prompt
    assert "DO NOT run `runner.py apply-outcome`" in prompt
    # Layer C — direct-edit prohibition, references the concrete loop-state path.
    assert "DO NOT edit `openspec/changes/demo/loop-state.json`" in prompt
    # Contract framing.
    assert "outcome" in prompt and "handoff_id" in prompt


@pytest.mark.parametrize("phase", ["INIT", "SUBMIT_PR"])
def test_state_only_phase_has_no_prohibitions(chdir_tmp: Path, phase: str) -> None:
    _seed(chdir_tmp, phase)
    prompt = _render(phase)
    assert "DO NOT run `runner.py apply-outcome`" not in prompt


def test_gatekeeper_readonly_phase_has_no_prohibitions(chdir_tmp: Path) -> None:
    _seed(chdir_tmp, "GATEKEEPER")
    prompt = _render("GATEKEEPER")
    assert "DO NOT run `runner.py apply-outcome`" not in prompt
