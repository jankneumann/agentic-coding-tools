"""Tests for LoopState v3 schema bump with phase_archetype field.

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/agent-coordinator/spec.md
      Requirement: LoopState Phase Archetype Field.
Contract: openspec/changes/add-per-phase-archetype-resolution/contracts/schemas/loop-state-v3.schema.json
Design decision: D7.
"""

from __future__ import annotations

import json
from pathlib import Path

import autopilot


def test_new_loop_state_default_phase_archetype_is_none() -> None:
    state = autopilot.LoopState()
    assert state.phase_archetype is None


def test_new_loop_state_schema_version_is_3() -> None:
    state = autopilot.LoopState()
    assert state.schema_version == 3


def test_phase_archetype_field_round_trips_through_save_load(tmp_path: Path) -> None:
    state = autopilot.LoopState(change_id="x", phase_archetype="architect")
    state_path = tmp_path / "loop-state.json"
    autopilot.save_state(state, state_path)

    loaded = autopilot.load_state(state_path)
    assert loaded.phase_archetype == "architect"
    assert loaded.schema_version == 3


def test_load_v2_snapshot_migrates_to_v3_with_null(tmp_path: Path) -> None:
    """Older v2 snapshots load with phase_archetype=None and rewrite to v3 on save."""
    legacy: dict[str, object] = {
        "schema_version": 2,
        "change_id": "legacy-feature",
        "current_phase": "IMPLEMENT",
        "iteration": 1,
        # Notice: no phase_archetype field
    }
    state_path = tmp_path / "loop-state.json"
    state_path.write_text(json.dumps(legacy) + "\n")

    state = autopilot.load_state(state_path)
    assert state.phase_archetype is None
    # The migration is applied: schema_version is bumped on the loaded instance.
    # (Actual file-on-disk gets schema_version=3 only after a save_state call.)
    assert state.schema_version == 3

    # Saving rewrites the file with v3.
    autopilot.save_state(state, state_path)
    on_disk = json.loads(state_path.read_text())
    assert on_disk["schema_version"] == 3
    assert on_disk["phase_archetype"] is None


def test_phase_archetype_set_explicitly() -> None:
    state = autopilot.LoopState(phase_archetype="reviewer")
    assert state.phase_archetype == "reviewer"
