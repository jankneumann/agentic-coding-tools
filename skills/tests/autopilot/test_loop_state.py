"""Tests for the LoopState schema and its forward migrations.

Spec: openspec/changes/add-per-phase-archetype-resolution/specs/agent-coordinator/spec.md
      Requirement: LoopState Phase Archetype Field.
      openspec/changes/encode-autopilot-gates-and-goal-gate-in-code/specs/
      skill-workflow/spec.md
      Requirement: Loop State Gate Records.
Contracts: contracts/events/{gate-request,gate-decision}.schema.json
Design decisions: D7 (both changes).
"""

from __future__ import annotations

import json
from pathlib import Path

import autopilot


def test_new_loop_state_default_phase_archetype_is_none() -> None:
    state = autopilot.LoopState()
    assert state.phase_archetype is None


def test_new_loop_state_schema_version_is_5() -> None:
    state = autopilot.LoopState()
    assert state.schema_version == 5


def test_phase_archetype_field_round_trips_through_save_load(tmp_path: Path) -> None:
    state = autopilot.LoopState(change_id="x", phase_archetype="architect")
    state_path = tmp_path / "loop-state.json"
    autopilot.save_state(state, state_path)

    loaded = autopilot.load_state(state_path)
    assert loaded.phase_archetype == "architect"
    assert loaded.schema_version == 5


def test_load_v2_snapshot_migrates_to_v5_with_defaults(tmp_path: Path) -> None:
    """Older v2 snapshots load with the current field defaults and rewrite on save."""
    legacy: dict[str, object] = {
        "schema_version": 2,
        "change_id": "legacy-feature",
        "current_phase": "IMPLEMENT",
        "iteration": 1,
        # Notice: no phase_archetype / force / gate_signals / gate_verdict fields
    }
    state_path = tmp_path / "loop-state.json"
    state_path.write_text(json.dumps(legacy) + "\n")

    state = autopilot.load_state(state_path)
    assert state.phase_archetype is None
    assert state.force is False
    assert state.gate_signals == {}
    assert state.gate_verdict is None
    # The migration is applied: schema_version is bumped on the loaded instance.
    # (Actual file-on-disk gets schema_version=5 only after a save_state call.)
    assert state.schema_version == 5

    # Saving rewrites the file with v5.
    autopilot.save_state(state, state_path)
    on_disk = json.loads(state_path.read_text())
    assert on_disk["schema_version"] == 5
    assert on_disk["phase_archetype"] is None


def test_phase_archetype_set_explicitly() -> None:
    state = autopilot.LoopState(phase_archetype="reviewer")
    assert state.phase_archetype == "reviewer"


# ---------------------------------------------------------------------------
# v5 gate fields (encode-autopilot-gates-and-goal-gate-in-code, tasks 2.1/2.2)
# ---------------------------------------------------------------------------


def _v4_snapshot() -> dict[str, object]:
    """A complete v4 loop state, including the fields a naive migration drops."""
    return {
        "schema_version": 4,
        "change_id": "legacy-v4",
        "current_phase": "VALIDATE",
        "iteration": 2,
        "total_iterations": 11,
        "max_phase_iterations": 3,
        "findings_trend": [4, 1],
        "blocking_findings": [{"id": "F1"}],
        "vendor_availability": {"claude": True},
        "packages_status": {"wp-a": "complete"},
        "package_authors": {"wp-a": "claude"},
        "implementation_strategy": {"wp-a": "parallel"},
        "memory_ids": ["m-1"],
        "handoff_ids": ["h-1"],
        "phase_history": [{"phase": "IMPLEMENT", "outcome": "complete"}],
        "last_handoff_id": "h-1",
        "started_at": "2026-08-01T00:00:00+00:00",
        "phase_started_at": "2026-08-01T01:00:00+00:00",
        "previous_phase": "IMPL_REVIEW",
        "escalation_reason": None,
        "val_review_enabled": True,
        "cli_review_enabled": False,
        "error": None,
        "phase_archetype": "validator",
        "force": True,
        "gate_signals": {"has_security_signal": True},
        "gate_verdict": "proceed_with_review",
    }


def test_v4_state_loads_as_v5_with_empty_gate_fields(tmp_path: Path) -> None:
    """A v4 file gains the three gate fields as empty — never as invented data."""
    state_path = tmp_path / "loop-state.json"
    state_path.write_text(json.dumps(_v4_snapshot()) + "\n")

    state = autopilot.load_state(state_path)

    assert state.schema_version == 5
    assert state.gate_decisions == []
    assert state.pending_gate is None
    assert state.goal_gate is None


def test_v4_migration_preserves_every_v4_field(tmp_path: Path) -> None:
    """phase_history in particular: the field a dataclass round-trip once dropped."""
    legacy = _v4_snapshot()
    state_path = tmp_path / "loop-state.json"
    state_path.write_text(json.dumps(legacy) + "\n")

    state = autopilot.load_state(state_path)

    for key, value in legacy.items():
        if key == "schema_version":
            continue
        assert getattr(state, key) == value, key


def test_gate_records_survive_the_dataclass_round_trip(tmp_path: Path) -> None:
    decisions = [
        {
            "gate": "proposal_approval",
            "outcome": "proceed",
            "resolution": "auto",
            "disposition": "auto",
            "reason": "auto-approved",
            "posture_present": True,
            "recorded_at": "2026-08-30T00:00:00+00:00",
        },
        {
            "gate": "merge",
            "outcome": "proceed",
            "resolution": "console_approved",
            "disposition": "block",
            "reason": "operator approved",
            "posture_present": False,
            "recorded_at": "2026-08-30T00:01:00+00:00",
            "merge_authorized": True,
        },
    ]
    pending = {
        "schema_version": 1,
        "change_id": "demo",
        "gate": "merge",
        "phase": "SUBMIT_PR",
        "requested_at": "2026-08-30T00:02:00+00:00",
        "prompt": "Authorize merging this pull request?",
        "context": {"pr_url": None},
        "posture": {"disposition": "block", "posture_present": False},
    }
    state = autopilot.LoopState(
        change_id="demo",
        gate_decisions=decisions,
        pending_gate=pending,
        goal_gate={"verdict": "passed", "reason": "ok", "evidence": {}},
    )
    state_path = tmp_path / "loop-state.json"
    autopilot.save_state(state, state_path)
    first = state_path.read_text()

    reloaded = autopilot.load_state(state_path)
    assert reloaded.gate_decisions == decisions
    assert reloaded.pending_gate == pending
    assert reloaded.goal_gate == {"verdict": "passed", "reason": "ok", "evidence": {}}

    autopilot.save_state(reloaded, state_path)
    assert state_path.read_text() == first
