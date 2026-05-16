from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import coordination_bridge
import phase_agent
from provider_dispatch import (
    PhaseDispatchPayload,
    dispatch_phase,
    normalize_dispatch_result,
)


def _seed_loop_state(repo_root: Path, change_id: str, **overrides: Any) -> None:
    change_dir = repo_root / "openspec" / "changes" / change_id
    change_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "schema_version": 3,
        "change_id": change_id,
        "current_phase": "IMPLEMENT",
        "iteration": 0,
        "total_iterations": 0,
        "max_phase_iterations": 3,
        "handoff_ids": [],
        "last_handoff_id": None,
        "previous_phase": None,
        "phase_archetype": None,
        "loc_estimate": 250,
    }
    state.update(overrides)
    (change_dir / "loop-state.json").write_text(json.dumps(state, indent=2) + "\n")


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_build_phase_dispatch_payload_returns_provider_neutral_payload(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_loop_state(workspace, "demo")
    monkeypatch.setattr(
        coordination_bridge,
        "try_resolve_archetype_for_phase",
        lambda phase, signals=None, **kwargs: {
            "model": "gpt-5.5",
            "system_prompt": "You are a focused implementer.",
            "archetype": "implementer",
            "reasons": ["phase=IMPLEMENT maps to archetype=implementer"],
        },
    )

    payload = phase_agent.build_phase_dispatch_payload(
        phase="IMPLEMENT",
        change_id="demo",
        provider="codex",
    )

    assert payload["schema_version"] == 1
    assert payload["phase"] == "IMPLEMENT"
    assert payload["provider"] == "codex"
    assert payload["model"] == "gpt-5.5"
    assert payload["isolation"] == "worktree"
    assert payload["archetype"] == "implementer"
    assert "complete" in payload["expected_outcomes"]


def test_normalize_tuple_result() -> None:
    payload = PhaseDispatchPayload(
        schema_version=1,
        change_id="demo",
        phase="IMPLEMENT",
        provider="codex",
        archetype="implementer",
        model="gpt-5.5",
        prompt="do work",
        system_prompt=None,
        isolation="worktree",
        expected_outcomes=["complete", "failed"],
    )

    result = normalize_dispatch_result(("complete", "handoff-1"), payload, "harness")

    assert result.outcome == "complete"
    assert result.handoff_id == "handoff-1"
    assert result.provider == "codex"
    assert result.model_used == "gpt-5.5"


def test_dispatch_dry_run_normalizes_codex_result() -> None:
    payload = PhaseDispatchPayload(
        schema_version=1,
        change_id="demo",
        phase="IMPLEMENT",
        provider="codex",
        archetype="implementer",
        model="gpt-5.5",
        prompt="do work",
        system_prompt=None,
        isolation="worktree",
        expected_outcomes=["complete", "failed"],
    )

    result = dispatch_phase(payload, dry_run=True)

    assert result.outcome == "complete"
    assert result.handoff_id.startswith("dry-run:")
    assert result.dispatch_tier == "dry_run"
    assert result.warnings == []


def test_missing_adapter_falls_back_with_warning() -> None:
    payload = PhaseDispatchPayload(
        schema_version=1,
        change_id="demo",
        phase="IMPLEMENT",
        provider="unknown",
        archetype="implementer",
        model="some-model",
        prompt="do work",
        system_prompt=None,
        isolation="worktree",
        expected_outcomes=["complete", "failed"],
    )

    result = dispatch_phase(payload, dry_run=False)

    assert result.outcome == "failed"
    assert result.dispatch_tier == "fallback"
    assert any("adapter unavailable" in warning for warning in result.warnings)
