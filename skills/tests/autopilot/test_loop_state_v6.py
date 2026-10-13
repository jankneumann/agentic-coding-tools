"""LoopState v6: park and degradations (dispatch-contract Loop State Parks and
Degradations, D11), plus GATEKEEPER review scheduling on the host-driven path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import autopilot
import runner


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _seed(workspace: Path, **fields: Any) -> Path:
    state = autopilot.LoopState(change_id="demo", current_phase="IMPLEMENT")
    for key, value in fields.items():
        setattr(state, key, value)
    path = workspace / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(state, path)
    return path


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def test_version_5_state_migrates(tmp_path: Path) -> None:
    v5 = {
        "schema_version": 5,
        "change_id": "legacy",
        "current_phase": "VALIDATE",
        "gate_decisions": [{"gate": "merge"}],
        "pending_gate": None,
        "goal_gate": None,
        "phase_history": [{"phase": "PLAN", "outcome": "created", "at": "t"}],
    }
    path = tmp_path / "loop-state.json"
    path.write_text(json.dumps(v5))

    state = autopilot.load_state(path)

    assert state.schema_version == 6
    assert state.park is None
    assert state.degradations == []
    assert state.gate_decisions == v5["gate_decisions"]
    assert state.phase_history == v5["phase_history"]
    assert state.current_phase == "VALIDATE"


def test_a_park_blocks_transitions(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _seed(workspace, park={"kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["codex"]})

    rc = runner.main(
        ["apply-outcome", "--change-id", "demo", "--phase", "IMPLEMENT", "--outcome", "complete", "--handoff-id", "h"]
    )

    assert rc != 0
    assert "capability_unavailable" in capsys.readouterr().err
    assert _read(path)["current_phase"] == "IMPLEMENT"
    with pytest.raises(autopilot.ParkActive):
        autopilot._apply_transition(autopilot.load_state(path), "complete")
    assert runner.main(["transition", "--change-id", "demo", "--outcome", "complete"]) == 2
    assert _read(path)["current_phase"] == "IMPLEMENT"


def test_an_unknown_degradation_code_is_rejected(workspace: Path) -> None:
    path = _seed(workspace)
    before = path.read_bytes()

    assert runner.main(["record-degradation", "demo", "--code", "made_up", "--phase", "PLAN_REVIEW"]) == 2
    assert path.read_bytes() == before


def test_a_known_degradation_is_recorded_once(workspace: Path) -> None:
    path = _seed(workspace)
    argv = ["record-degradation", "demo", "--code", "review_skipped", "--phase", "PLAN_REVIEW", "--detail", "one lane"]
    assert runner.main(argv) == 0
    assert runner.main(argv) == 0
    assert _read(path)["degradations"] == [
        {"code": "review_skipped", "phase": "PLAN_REVIEW", "detail": "one lane"}
    ]


def test_the_park_command_is_redacted_before_it_is_stored(workspace: Path) -> None:
    path = _seed(workspace)

    rc = runner.main(
        [
            "park", "demo", "--kind", "permission_blocked",
            "--tool", "Bash", "--rule", "Bash(curl *)",
            "--command", 'curl -H "Authorization: Bearer abc123def456ghi789"',
            "--reason", "network egress",
        ]
    )

    assert rc == 0
    park = _read(path)["park"]
    assert park["kind"] == "permission_blocked"
    assert "abc123def456ghi789" not in json.dumps(park)
    assert "[REDACTED:" in park["command"]


def test_capability_park_records_sorted_missing_lanes(workspace: Path) -> None:
    path = _seed(workspace, current_phase="PLAN_REVIEW")
    rc = runner.main(
        ["park", "demo", "--kind", "capability_unavailable", "--phase", "PLAN_REVIEW",
         "--missing-lane", "gemini", "--missing-lane", "codex"]
    )
    assert rc == 0
    assert _read(path)["park"]["missing_lanes"] == ["codex", "gemini"]


def test_escalate_resume_answer_clears_the_park(workspace: Path) -> None:
    path = _seed(workspace, park={"kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["codex"]})

    rc = runner.main(["gate-answer", "demo", "--gate", "escalate_resume", "--decision", "approved"])

    assert rc == 0
    state = _read(path)
    assert state["park"] is None
    assert state["gate_decisions"][-1]["gate"] == "escalate_resume"
    assert state["gate_decisions"][-1]["provenance"]["source"] == "human"


def test_gatekeeper_proceed_with_review_schedules_val_review_on_the_host_path(workspace: Path) -> None:
    """GATEKEEPER `proceed_with_review` applied through `runner.py transition`
    (the host-driven path) enables VAL_REVIEW, as run_loop's handler does."""
    path = _seed(workspace, current_phase="GATEKEEPER", val_review_enabled=False)

    assert runner.main(["transition", "--change-id", "demo", "--outcome", "proceed_with_review"]) == 0

    state = _read(path)
    assert state["current_phase"] == "PLAN"
    assert state["val_review_enabled"] is True
    assert state["gate_verdict"] == "proceed_with_review"


def test_gatekeeper_plain_proceed_leaves_val_review_alone(workspace: Path) -> None:
    path = _seed(workspace, current_phase="GATEKEEPER", val_review_enabled=False)
    assert runner.main(["transition", "--change-id", "demo", "--outcome", "proceed"]) == 0
    assert _read(path)["val_review_enabled"] is False
