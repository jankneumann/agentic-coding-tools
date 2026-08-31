"""Tests for the ``Gate.REPLAN_REQUIRED`` evaluation in the orchestrator.

Covers roadmap-orchestration scenarios *Replan gate proceeds and emits a
request*, *Replan gate blocked leaves items parked*, and *Orchestrator never
performs the replan itself*.

The gate evaluator is injected: these tests never construct the real
bridge-backed gate, which is exactly the seam that keeps
``skills/autopilot-roadmap/scripts/`` free of LLM and network calls (see
``test_host_assisted_invariant.py``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from models import (
    Effort,
    ItemStatus,
    Policy,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
)
from orchestrator import execute_roadmap
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

_REPO_ROOT = Path(__file__).resolve().parents[3]

# `shared.approval_gate` does `from shared.trust_posture import ...`, so the
# PARENT of the package must be on the path.
sys.path.insert(0, str(_REPO_ROOT / "skills"))

from shared.approval_gate import (  # noqa: E402
    ApprovalDecision,
    Outcome,
    Resolution,
)
from shared.trust_posture import Disposition, Gate  # noqa: E402

_CONTRACTS = (
    _REPO_ROOT
    / "openspec" / "schemas"
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _replan_request_validator() -> Draft202012Validator:
    """Validator that resolves the sibling $ref to gate-decision.schema.json."""
    registry = Registry()
    schemas = {}
    for name in ("replan-request", "gate-decision"):
        schema = json.loads((_CONTRACTS / f"{name}.schema.json").read_text())
        schemas[name] = schema
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        registry = registry.with_resources(
            [(f"{name}.schema.json", resource), (schema["$id"], resource)]
        )
    return Draft202012Validator(schemas["replan-request"], registry=registry)


class FakeGateEvaluator:
    """Records every ``evaluate`` call and returns a canned decision."""

    def __init__(self, outcome: Outcome) -> None:
        self._outcome = outcome
        self.calls: list[tuple[Gate, dict]] = []

    def evaluate(self, gate, context):
        self.calls.append((gate, dict(context)))
        if self._outcome is Outcome.PROCEED:
            return ApprovalDecision(
                gate=gate,
                outcome=Outcome.PROCEED,
                resolution=Resolution.AUTO,
                disposition=Disposition.AUTO,
                reason="posture auto",
                posture_present=True,
            )
        return ApprovalDecision(
            gate=gate,
            outcome=Outcome.BLOCKED,
            resolution=Resolution.POSTURE_BLOCK,
            disposition=Disposition.BLOCK,
            reason="posture blocks replan",
            posture_present=True,
        )


def _write_roadmap(workspace: Path, items: list[RoadmapItem]) -> None:
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="test-roadmap",
        source_proposal="test-proposal.md",
        items=items,
        status=RoadmapStatus.APPROVED,
        policy=Policy(),
    )
    (workspace / "roadmap.yaml").write_text(
        yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False)
    )


def _fan_out_items() -> list[RoadmapItem]:
    """ri-01 fails; ri-02 and ri-03 depend on it; ri-04 is unrelated."""
    return [
        RoadmapItem("ri-01", "Will fail", ItemStatus.APPROVED, 1, Effort.S),
        RoadmapItem(
            "ri-02", "Dependent A", ItemStatus.APPROVED, 2, Effort.S, depends_on=["ri-01"]
        ),
        RoadmapItem(
            "ri-03", "Dependent B", ItemStatus.APPROVED, 3, Effort.S, depends_on=["ri-01"]
        ),
        RoadmapItem("ri-04", "Unrelated", ItemStatus.APPROVED, 4, Effort.S),
    ]


def _dispatcher(dispatched: list[str], *, replan: bool):
    """Fails ri-01 at 'implementing', succeeds everywhere else."""

    def dispatch(item_id, phase, context):
        dispatched.append(item_id)
        if item_id == "ri-01" and phase == "implementing":
            if replan:
                return {"outcome": "failed:design dead-end", "replan": True}
            return "failed:design dead-end"
        return "success"

    return dispatch


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class TestReplanGateProceeds:
    def test_writes_schema_valid_request_and_returns_replan_requested(self, tmp_path):
        _write_roadmap(tmp_path, _fan_out_items())
        evaluator = FakeGateEvaluator(Outcome.PROCEED)
        dispatched: list[str] = []

        result = execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher(dispatched, replan=True),
            gate_evaluator=evaluator,
        )

        assert result["status"] == "replan_requested"

        request_path = tmp_path / "replan-request.json"
        assert request_path.exists()
        payload = json.loads(request_path.read_text())
        _replan_request_validator().validate(payload)

        assert payload["roadmap_id"] == "test-roadmap"
        assert payload["failed_item_id"] == "ri-01"
        assert sorted(payload["replan_required_items"]) == ["ri-02", "ri-03"]
        assert payload["gate_decision"]["gate"] == "replan_required"
        assert payload["gate_decision"]["outcome"] == "proceed"

    def test_gate_evaluated_once_per_failure_not_per_dependent(self, tmp_path):
        _write_roadmap(tmp_path, _fan_out_items())
        evaluator = FakeGateEvaluator(Outcome.PROCEED)

        execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher([], replan=True),
            gate_evaluator=evaluator,
        )

        assert len(evaluator.calls) == 1
        gate, context = evaluator.calls[0]
        assert gate is Gate.REPLAN_REQUIRED
        assert context["failed_item_id"] == "ri-01"
        assert sorted(context["replan_required_items"]) == ["ri-02", "ri-03"]

    def test_parked_items_are_not_dispatched(self, tmp_path):
        _write_roadmap(tmp_path, _fan_out_items())
        dispatched: list[str] = []

        execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher(dispatched, replan=True),
            gate_evaluator=FakeGateEvaluator(Outcome.PROCEED),
        )

        assert "ri-02" not in dispatched
        assert "ri-03" not in dispatched

    def test_roadmap_records_replan_required(self, tmp_path):
        _write_roadmap(tmp_path, _fan_out_items())

        execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher([], replan=True),
            gate_evaluator=FakeGateEvaluator(Outcome.PROCEED),
        )

        data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        statuses = {i["item_id"]: i["status"] for i in data["items"]}
        assert statuses["ri-01"] == "failed"
        assert statuses["ri-02"] == "replan_required"
        assert statuses["ri-03"] == "replan_required"


class TestReplanGateBlocked:
    def test_writes_nothing_and_continues(self, tmp_path):
        _write_roadmap(tmp_path, _fan_out_items())
        evaluator = FakeGateEvaluator(Outcome.BLOCKED)
        dispatched: list[str] = []

        result = execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher(dispatched, replan=True),
            gate_evaluator=evaluator,
        )

        assert not (tmp_path / "replan-request.json").exists()
        assert result["status"] != "replan_requested"
        # The unrelated ready item still runs.
        assert "ri-04" in dispatched
        assert "ri-02" not in dispatched

    def test_items_stay_parked_and_decision_persisted_in_checkpoint(self, tmp_path):
        _write_roadmap(tmp_path, _fan_out_items())

        execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher([], replan=True),
            gate_evaluator=FakeGateEvaluator(Outcome.BLOCKED),
        )

        data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        statuses = {i["item_id"]: i["status"] for i in data["items"]}
        assert statuses["ri-02"] == "replan_required"
        assert statuses["ri-03"] == "replan_required"

        checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
        decisions = checkpoint["gate_decisions"]
        assert len(decisions) == 1
        assert decisions[0]["gate"] == "replan_required"
        assert decisions[0]["outcome"] == "blocked"
        assert decisions[0]["resolution"] == "posture_block"
        Draft202012Validator(
            json.loads((_CONTRACTS / "gate-decision.schema.json").read_text())
        ).validate(decisions[0])


class TestNoReplanSignal:
    def test_plain_failure_never_reaches_the_gate(self, tmp_path):
        _write_roadmap(tmp_path, _fan_out_items())
        evaluator = FakeGateEvaluator(Outcome.PROCEED)

        result = execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher([], replan=False),
            gate_evaluator=evaluator,
        )

        assert evaluator.calls == []
        assert not (tmp_path / "replan-request.json").exists()
        assert result["status"] != "replan_requested"

        data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        statuses = {i["item_id"]: i["status"] for i in data["items"]}
        assert statuses["ri-02"] == "blocked"
        assert statuses["ri-03"] == "blocked"

    def test_default_evaluator_is_never_built_without_a_replan(self, tmp_path, monkeypatch):
        """The real gate opens a coordinator transport; it must stay unbuilt
        on every run that never parks an item in replan_required."""
        import orchestrator

        def _boom():
            raise AssertionError("default gate evaluator must not be constructed")

        monkeypatch.setattr(orchestrator, "_build_default_gate_evaluator", _boom)
        _write_roadmap(tmp_path, _fan_out_items())

        result = execute_roadmap(tmp_path, dispatch_fn=_dispatcher([], replan=False))

        assert result["status"] in {"completed", "partial", "blocked_all"}


class TestHostAssisted:
    def test_orchestrator_makes_no_network_call_to_replan(self, tmp_path):
        """*Orchestrator never performs the replan itself*: the request is a
        file in the workspace, and nothing in the module reaches the network."""
        source = (
            _REPO_ROOT / "skills" / "autopilot-roadmap" / "scripts" / "orchestrator.py"
        ).read_text()
        for forbidden in ("requests.", "urllib.request", "urlopen", "http.client", "socket."):
            assert forbidden not in source

    @pytest.mark.parametrize("outcome", [Outcome.PROCEED, Outcome.BLOCKED])
    def test_no_replan_is_performed_by_the_orchestrator(self, tmp_path, outcome):
        """Whatever the gate says, the roadmap item set is never re-decomposed."""
        _write_roadmap(tmp_path, _fan_out_items())

        execute_roadmap(
            tmp_path,
            dispatch_fn=_dispatcher([], replan=True),
            gate_evaluator=FakeGateEvaluator(outcome),
        )

        data = yaml.safe_load((tmp_path / "roadmap.yaml").read_text())
        assert [i["item_id"] for i in data["items"]] == ["ri-01", "ri-02", "ri-03", "ri-04"]
