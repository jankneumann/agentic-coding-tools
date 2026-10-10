"""Gate authority and re-evaluation on resume (dispatch-contract D5, D10a).

A dispatched child (launch marker present) applies only its marker's
gate_answer; a standalone run re-evaluates its own pending gate when the
posture digest moved; a human decision is final.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

import autopilot
import runner

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.approval_gate import ApprovalGate  # noqa: E402
from shared.trust_posture import load_posture, posture_digest  # noqa: E402

_REF_Y = "gate-decision:22222222-3333-4444-8555-666666666666"
_REF_X = "gate-decision:99999999-3333-4444-8555-666666666666"


class _Audit:
    def record(self, _record: dict[str, Any]) -> bool:
        return True


class _Coordinator:
    def request_approval(self, **_kwargs: Any) -> str:
        return "approval-1"

    def push_notification(self, **_kwargs: Any) -> bool:
        return False

    def check_approval(self, _approval_id: str) -> str:
        return "pending"


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)

    def build(change_id: str, repo_root: Path) -> ApprovalGate:
        # The real gate (posture file and launch-marker seam at repo_root);
        # only the transport and the audit sink stay off the network.
        return ApprovalGate(
            coordinator=_Coordinator(),
            audit=_Audit(),
            agent_id=f"autopilot:{change_id}",
            repo_root=str(repo_root),
            sleep=lambda _s: None,
            marker_reader=autopilot.launch_marker_reader(change_id, repo_root),
        )

    monkeypatch.setattr(autopilot, "_build_gate_evaluator", build)
    return tmp_path


def _posture(root: Path, **gates: str) -> str:
    doc = {"schema_version": 1, "gates": {k: {"disposition": v} for k, v in gates.items()}}
    (root / "TRUST_POSTURE.md").write_text("---\n" + yaml.safe_dump(doc) + "---\n")
    return posture_digest(load_posture(root))


def _marker(root: Path, **fields: Any) -> None:
    folder = root / ".supervised-dispatch" / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 2,
        "dispatch_id": "batch-0123456789abcdef01234567:ri-01:attempt-1",
        "generation": 2,
        "owner_nonce": "owner-nonce-0000000002",
        "roadmap_approval_ref": "gate-decision:11111111-2222-4333-8444-555555555555",
    }
    record.update(fields)
    (folder / "ri-01-attempt-1.marker").write_text(json.dumps(record))


def _seed(root: Path, *, pending: dict[str, Any] | None = None, **fields: Any) -> Path:
    state = autopilot.LoopState(change_id="demo", current_phase=fields.pop("current_phase", "PLAN"))
    state.pending_gate = pending
    for key, value in fields.items():
        setattr(state, key, value)
    path = root / "openspec" / "changes" / "demo" / "loop-state.json"
    autopilot.save_state(state, path)
    return path


def _pending(gate: str, digest: str, *, edge: dict[str, str] | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": 1,
        "change_id": "demo",
        "gate": gate,
        "phase": "PLAN",
        "requested_at": "2026-10-01T00:00:00+00:00",
        "prompt": "Approve?",
        "context": {},
        "posture": {"disposition": "block", "posture_present": True, "posture_digest": digest},
    }
    if edge is not None:
        request["edge"] = edge
    return request


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# Dispatched child
# --------------------------------------------------------------------------- #


def test_a_dispatched_child_applies_the_supervisors_answer(workspace: Path) -> None:
    digest = _posture(workspace, proposal_approval="block")
    _marker(
        workspace,
        gate_answer={"gate": "proposal_approval", "decision": "approved", "approval_ref": _REF_Y},
    )
    path = _seed(workspace, pending=_pending("proposal_approval", digest, edge={"outcome": "created", "target": "PLAN_ITERATE"}))

    rc = runner.main(
        ["gate-answer", "demo", "--gate", "proposal_approval", "--decision", "approved", "--approval-ref", _REF_Y]
    )

    assert rc == 0
    state = _read(path)
    assert state["pending_gate"] is None
    assert state["gate_decisions"][-1]["provenance"] == {"source": "human", "approval_ref": _REF_Y}
    assert state["current_phase"] == "PLAN_ITERATE"


def test_a_posture_derived_supervisor_answer_keeps_posture_provenance(workspace: Path) -> None:
    digest = _posture(workspace, proposal_approval="block")
    supervisor_digest = "d" * 64
    _marker(
        workspace,
        gate_answer={
            "gate": "proposal_approval",
            "decision": "approved",
            "approval_ref": _REF_Y,
            "provenance": {"source": "posture", "posture_digest": supervisor_digest},
        },
    )
    path = _seed(workspace, pending=_pending("proposal_approval", digest, edge={"outcome": "created", "target": "PLAN_ITERATE"}))

    assert runner.main(
        ["gate-answer", "demo", "--gate", "proposal_approval", "--decision", "approved", "--approval-ref", _REF_Y]
    ) == 0
    assert _read(path)["gate_decisions"][-1]["provenance"] == {
        "source": "posture",
        "posture_digest": supervisor_digest,
    }


def test_a_dispatched_child_does_not_self_re_evaluate(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = _posture(workspace, pr_creation="block")
    _posture(workspace, pr_creation="auto")
    _marker(workspace)
    pending = _pending("pr_creation", old)
    path = _seed(workspace, pending=pending)

    assert runner.main(["gate-check", "demo"]) == 0
    assert json.loads(capsys.readouterr().out) == pending
    state = _read(path)
    assert state["pending_gate"] == pending
    assert state["gate_decisions"] == []


def test_posture_drift_between_child_and_supervisor_blocks_auto(workspace: Path) -> None:
    _posture(workspace, proposal_approval="auto")
    _marker(workspace, posture_digest="e" * 64)
    path = _seed(workspace)

    assert runner.main(["gate-check", "demo", "--gate", "proposal_approval"]) == 0

    state = _read(path)
    assert state["pending_gate"]["gate"] == "proposal_approval"
    assert "posture digest differs from dispatch" in state["gate_decisions"][-1]["reason"]


def test_a_mismatched_approval_reference_is_refused(workspace: Path) -> None:
    digest = _posture(workspace, proposal_approval="block")
    _marker(
        workspace,
        gate_answer={"gate": "proposal_approval", "decision": "approved", "approval_ref": _REF_Y},
    )
    path = _seed(workspace, pending=_pending("proposal_approval", digest))
    before = path.read_bytes()

    rc = runner.main(
        ["gate-answer", "demo", "--gate", "proposal_approval", "--decision", "approved", "--approval-ref", _REF_X]
    )

    assert rc == 2
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("gate", "decision"),
    [
        ("proposal_approval", "approved"),  # the supervisor rejected it
        ("pr_creation", "rejected"),  # a gate the answer is not for
    ],
)
def test_a_matching_reference_does_not_authorize_another_gate_or_decision(
    workspace: Path, gate: str, decision: str
) -> None:
    digest = _posture(workspace, proposal_approval="block", pr_creation="block")
    _marker(
        workspace,
        gate_answer={"gate": "proposal_approval", "decision": "rejected", "approval_ref": _REF_Y},
    )
    path = _seed(workspace, pending=_pending(gate, digest))
    before = path.read_bytes()

    rc = runner.main(
        ["gate-answer", "demo", "--gate", gate, "--decision", decision, "--approval-ref", _REF_Y]
    )

    assert rc == 2
    assert path.read_bytes() == before


def test_a_park_is_not_cleared_by_an_answer_for_another_gate(workspace: Path) -> None:
    _posture(workspace, escalate_resume="block")
    _marker(
        workspace,
        gate_answer={"gate": "proposal_approval", "decision": "approved", "approval_ref": _REF_Y},
    )
    park = {"kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["codex"], "reason": "quorum"}
    path = _seed(workspace, park=park)
    before = path.read_bytes()

    rc = runner.main(
        ["gate-answer", "demo", "--gate", "escalate_resume", "--decision", "approved", "--approval-ref", _REF_Y]
    )

    assert rc == 2
    assert path.read_bytes() == before


# --------------------------------------------------------------------------- #
# Standalone run
# --------------------------------------------------------------------------- #


def test_a_standalone_stale_posture_block_clears_without_an_answer(workspace: Path) -> None:
    old = _posture(workspace, pr_creation="block")
    path = _seed(workspace, pending=_pending("pr_creation", old))
    _posture(workspace, pr_creation="auto")

    rc = runner.main(["gate-check", "demo"])

    assert rc == runner.EXIT_NO_PENDING_GATE
    state = _read(path)
    assert state["pending_gate"] is None
    assert state["gate_decisions"][-1]["outcome"] == "proceed"
    assert state["gate_decisions"][-1]["provenance"]["source"] == "posture"


def test_a_standalone_block_under_a_new_posture_reparks_with_the_new_digest(workspace: Path) -> None:
    old = _posture(workspace, merge="block")
    path = _seed(workspace, pending=_pending("merge", old))
    new = _posture(workspace, merge="block", pr_creation="auto")

    assert runner.main(["gate-check", "demo"]) == 0
    assert _read(path)["pending_gate"]["posture"]["posture_digest"] == new


def test_an_unchanged_posture_is_not_re_evaluated(workspace: Path) -> None:
    digest = _posture(workspace, pr_creation="block")
    path = _seed(workspace, pending=_pending("pr_creation", digest))

    assert runner.main(["gate-check", "demo"]) == 0
    assert _read(path)["gate_decisions"] == []


def test_a_human_rejection_is_not_re_evaluated(workspace: Path) -> None:
    _posture(workspace, merge="block")
    rejected = {
        "gate": "merge",
        "outcome": "blocked",
        "resolution": "console_rejected",
        "disposition": "block",
        "reason": "rejected",
        "posture_present": True,
        "recorded_at": "2026-10-01T00:00:00+00:00",
        "provenance": {"source": "human", "approval_ref": None},
    }
    path = _seed(workspace, current_phase="ESCALATE", previous_phase="SUBMIT_PR", gate_decisions=[rejected])
    _posture(workspace, merge="auto")

    rc = runner.main(["gate-check", "demo", "--gate", "merge"])

    assert rc == runner.EXIT_GATE_PARKED
    state = _read(path)
    assert state["gate_decisions"] == [rejected]
    assert state["current_phase"] == "ESCALATE"


def _human(gate: str, outcome: str, at: str) -> dict[str, Any]:
    return {
        "gate": gate,
        "outcome": outcome,
        "resolution": "console_approved" if outcome == "proceed" else "console_rejected",
        "disposition": "block",
        "reason": outcome,
        "posture_present": True,
        "recorded_at": at,
        "provenance": {"source": "human", "approval_ref": None},
    }


def test_an_operator_resume_after_a_human_rejection_lets_the_gate_be_asked_again(
    workspace: Path,
) -> None:
    """The rejection's subject ends at a later human escalate_resume approval;
    otherwise a rejected gate could never be asked again in this run."""
    rejected = _human("merge", "blocked", "2026-10-01T00:00:00+00:00")
    resumed = _human("escalate_resume", "proceed", "2026-10-01T01:00:00+00:00")
    path = _seed(workspace, current_phase="SUBMIT_PR", gate_decisions=[rejected, resumed])
    _posture(workspace, merge="block")

    rc = runner.main(["gate-check", "demo", "--gate", "merge"])

    assert rc == 0
    state = _read(path)
    assert state["pending_gate"]["gate"] == "merge"
    assert state["gate_decisions"][-1]["provenance"]["source"] == "posture"


def test_a_posture_derived_resume_does_not_end_a_human_rejection(workspace: Path) -> None:
    rejected = _human("merge", "blocked", "2026-10-01T00:00:00+00:00")
    auto_resume = dict(
        _human("escalate_resume", "proceed", "2026-10-01T01:00:00+00:00"),
        resolution="auto",
        provenance={"source": "posture", "posture_digest": "0" * 64},
    )
    path = _seed(workspace, current_phase="SUBMIT_PR", gate_decisions=[rejected, auto_resume])
    _posture(workspace, merge="auto")

    rc = runner.main(["gate-check", "demo", "--gate", "merge"])

    assert rc == runner.EXIT_GATE_PARKED
    state = _read(path)
    assert state["gate_decisions"] == [rejected, auto_resume]
    # Parked where only an operator resume clears it, not silently stuck.
    assert state["current_phase"] == "ESCALATE"
    assert state["previous_phase"] == "SUBMIT_PR"


# --------------------------------------------------------------------------- #
# Cloud worker (no launch marker; roadmap scope committed at HEAD)
# --------------------------------------------------------------------------- #

_ROADMAP_APPROVAL = "40776beb-63e5-4a06-b7b9-b349f3a918df"


def _git(root: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _commit_scope(root: Path, *, resolution: str = "console_approved") -> None:
    checkpoint = {
        "gate_decisions": [
            {
                "decision_id": _ROADMAP_APPROVAL,
                "gate": "roadmap_approval",
                "outcome": "proceed" if resolution == "console_approved" else "blocked",
                "resolution": resolution,
            }
        ],
        "dispatch_attempts": [
            {
                "dispatch_id": "batch-0123456789abcdef01234567:ri-01:attempt-1",
                "change_id": "demo",
                "attempt": 1,
                "lease_generation": 2,
                "roadmap_approval_ref": f"gate-decision:{_ROADMAP_APPROVAL}",
            }
        ],
    }
    path = root / "openspec" / "roadmaps" / "rm" / "checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint))
    if not (root / ".git").exists():
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "t@example.com")
        _git(root, "config", "user.name", "t")
    _git(root, "add", "openspec/roadmaps")
    _git(root, "commit", "-q", "-m", "checkpoint")


def _unscoped_park(workspace: Path) -> Path:
    digest = _posture(workspace, proposal_approval="auto")
    unscoped = {
        "gate": "proposal_approval",
        "outcome": "blocked",
        "resolution": "posture_block",
        "disposition": "block",
        "reason": "unscoped fallback",
        "posture_present": True,
        "recorded_at": "2026-10-01T00:00:00+00:00",
        "provenance": {"source": "posture", "posture_digest": digest},
        "scope": "unscoped",
    }
    pending = _pending("proposal_approval", digest, edge={"outcome": "created", "target": "PLAN_ITERATE"})
    return _seed(workspace, pending=pending, gate_decisions=[unscoped])


def test_a_cloud_worker_re_evaluates_once_its_roadmap_scope_is_committed(workspace: Path) -> None:
    path = _unscoped_park(workspace)
    _commit_scope(workspace)

    rc = runner.main(["gate-check", "demo"])

    assert rc == runner.EXIT_NO_PENDING_GATE
    state = _read(path)
    assert state["pending_gate"] is None
    assert state["gate_decisions"][-1]["resolution"] == "auto"
    assert state["gate_decisions"][-1]["scope"] == "roadmap_approval"
    assert state["current_phase"] == "PLAN_ITERATE"


def test_a_cloud_worker_without_an_approved_scope_stays_parked(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _unscoped_park(workspace)
    _commit_scope(workspace, resolution="posture_block")
    before = _read(path)

    assert runner.main(["gate-check", "demo"]) == 0
    assert json.loads(capsys.readouterr().out) == before["pending_gate"]
    assert _read(path) == before
