"""Gate-decision provenance and posture-drift parking (dispatch-contract D5, D10a)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills"))

from shared import trust_posture as tp  # noqa: E402
from shared.approval_gate import (  # noqa: E402
    POSTURE_DRIFT_REASON,
    ApprovalGate,
    Outcome,
    Resolution,
    build_gate_decision_record,
    console_decision,
)
from shared.trust_posture import Gate  # noqa: E402

_SCHEMAS = REPO_ROOT / "openspec" / "schemas"
_REF = "gate-decision:11111111-2222-4333-8444-555555555555"


def _write(root: Path, gates: dict[str, Any]) -> None:
    (root / tp.DEFAULT_CONTRACT_FILENAME).write_text(
        "---\n" + yaml.safe_dump({"schema_version": 1, "gates": gates}) + "---\n",
        encoding="utf-8",
    )


class _Audit:
    def record(self, _record: dict[str, Any]) -> bool:
        return True


class _Coordinator:
    def __init__(self, status: str) -> None:
        self.status = status

    def request_approval(self, **_kwargs: Any) -> str:
        return "approval-1"

    def push_notification(self, **_kwargs: Any) -> bool:
        return True

    def check_approval(self, _approval_id: str) -> str:
        return self.status


def _gate(root: Path, *, marker: Any = None, status: str = "pending") -> ApprovalGate:
    return ApprovalGate(
        coordinator=_Coordinator(status),
        audit=_Audit(),
        repo_root=str(root),
        sleep=lambda _s: None,
        marker_reader=lambda _ctx: marker,
    )


def _validate(record: dict[str, Any]) -> None:
    schema = json.loads((_SCHEMAS / "gate-decision.schema.json").read_text())
    jsonschema.validate(record, schema)


def test_posture_resolutions_carry_the_posture_digest(tmp_path: Path) -> None:
    _write(tmp_path, {"pr_creation": {"disposition": "auto"}})
    digest = tp.posture_digest(tp.load_posture(tmp_path))
    for gate in (Gate.PR_CREATION, Gate.MERGE):
        decision = _gate(tmp_path).evaluate(gate, {"change_id": "demo"})
        assert decision.provenance == {"source": "posture", "posture_digest": digest}
        record = build_gate_decision_record(decision, phase="PLAN")
        assert record["provenance"]["posture_digest"] == digest
        _validate(record)


def test_coordinator_answers_are_human_provenance(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"merge": {"disposition": "notify_with_timeout", "timeout_seconds": 5, "default_action": "block"}},
    )
    decision = _gate(tmp_path, status="approved").evaluate(Gate.MERGE, {})
    assert decision.resolution is Resolution.APPROVED
    assert decision.provenance == {"source": "human", "approval_ref": None}
    _validate(build_gate_decision_record(decision, phase="SUBMIT_PR"))


def test_console_decisions_record_their_approval_reference() -> None:
    decision = console_decision(
        Gate.PROPOSAL_APPROVAL,
        {"disposition": "block", "posture_present": True},
        True,
        None,
        approval_ref=_REF,
    )
    assert decision.provenance == {"source": "human", "approval_ref": _REF}
    record = build_gate_decision_record(decision, phase="PLAN")
    _validate(record)
    bare = console_decision(Gate.MERGE, {}, False, "no")
    assert bare.provenance == {"source": "human", "approval_ref": None}


def test_dispatched_posture_drift_takes_no_auto(tmp_path: Path) -> None:
    """D5/D10a: a worktree posture whose digest differs from the marker's parks."""
    _write(tmp_path, {"pr_creation": {"disposition": "auto"}})
    marker = {"roadmap_approval_ref": _REF, "posture_digest": "0" * 64}
    decision = _gate(tmp_path, marker=marker).evaluate(Gate.PR_CREATION, {"change_id": "demo"})
    assert decision.outcome is Outcome.BLOCKED
    assert decision.resolution is Resolution.POSTURE_BLOCK
    assert POSTURE_DRIFT_REASON in decision.reason


def test_dispatched_matching_posture_keeps_auto(tmp_path: Path) -> None:
    _write(tmp_path, {"pr_creation": {"disposition": "auto"}})
    marker = {
        "roadmap_approval_ref": _REF,
        "posture_digest": tp.posture_digest(tp.load_posture(tmp_path)),
    }
    decision = _gate(tmp_path, marker=marker).evaluate(Gate.PR_CREATION, {"change_id": "demo"})
    assert decision.outcome is Outcome.PROCEED
