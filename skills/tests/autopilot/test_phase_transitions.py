"""Layer D regression tests for the orchestrator next-phase decision.

Spec: openspec/changes/fix-autopilot-archetype-and-apply-outcome/specs/
      skill-workflow/spec.md
      Requirement: "Orchestrator's Next-Phase Decision Matches the Canonical
                    State Machine"

The V2 bug transitioned IMPLEMENT=complete -> CLEANUP (not a state in the
autopilot state machine). These tests pin the correct mapping to the
centralized TRANSITIONS table in autopilot.py and guard against regressions
back to CLEANUP or any distributed/ad-hoc control flow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import autopilot
import pytest


def _seed_state(repo_root: Path, **overrides: Any) -> autopilot.LoopState:
    change_dir = repo_root / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True, exist_ok=True)
    state = autopilot.LoopState(change_id="demo", current_phase="IMPLEMENT")
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


# ---------------------------------------------------------------------------
# 6.6 — IMPLEMENT=complete -> IMPL_ITERATE (never CLEANUP)
# ---------------------------------------------------------------------------


def test_implement_complete_goes_to_impl_iterate(tmp_path: Path) -> None:
    state = _seed_state(
        tmp_path,
        current_phase="IMPLEMENT",
        phase_history=[{"phase": "IMPLEMENT", "outcome": "complete"}],
    )
    assert autopilot.transition(state, "complete") == "IMPL_ITERATE"


def test_implement_complete_is_not_cleanup(tmp_path: Path) -> None:
    state = _seed_state(tmp_path, current_phase="IMPLEMENT")
    next_phase = autopilot.transition(state, "complete")
    assert next_phase != "CLEANUP"


def test_cleanup_is_not_a_state_in_the_machine() -> None:
    # CLEANUP is a separate user-invoked skill, not an autopilot phase.
    assert "CLEANUP" not in autopilot.TRANSITIONS
    for _phase, table in autopilot.TRANSITIONS.items():
        assert "CLEANUP" not in table.values()


# ---------------------------------------------------------------------------
# IMPL_ITERATE=complete depends on cli_review_enabled
# ---------------------------------------------------------------------------


def test_impl_iterate_complete_with_cli_review(tmp_path: Path) -> None:
    state = _seed_state(
        tmp_path, current_phase="IMPL_ITERATE", cli_review_enabled=True,
    )
    assert autopilot.transition(state, "complete") == "IMPL_REVIEW"


def test_impl_iterate_complete_without_cli_review(tmp_path: Path) -> None:
    state = _seed_state(
        tmp_path, current_phase="IMPL_ITERATE", cli_review_enabled=False,
    )
    assert autopilot.transition(state, "complete") == "VALIDATE"


# ---------------------------------------------------------------------------
# Centralized structure (spec: decision logic is a single auditable structure)
# ---------------------------------------------------------------------------


def test_transitions_is_a_single_centralized_table() -> None:
    assert isinstance(autopilot.TRANSITIONS, dict)
    assert autopilot.TRANSITIONS["IMPLEMENT"]["complete"] == "IMPL_ITERATE"
    assert autopilot.TRANSITIONS["SUBMIT_PR"]["created"] == "DONE"


def test_state_round_trip_preserves_phase_history(tmp_path: Path) -> None:
    """phase_history survives save/load (not dropped by the dataclass)."""
    path = tmp_path / "loop-state.json"
    state = autopilot.LoopState(
        change_id="demo",
        current_phase="IMPLEMENT",
        phase_history=[{"phase": "IMPLEMENT", "outcome": "complete"}],
    )
    autopilot.save_state(state, path)
    reloaded = autopilot.load_state(path)
    assert reloaded.phase_history == [{"phase": "IMPLEMENT", "outcome": "complete"}]
    # Confirm it is actually serialized to disk.
    assert "phase_history" in json.loads(path.read_text())
