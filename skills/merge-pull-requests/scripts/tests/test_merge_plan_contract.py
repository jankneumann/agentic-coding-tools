"""Contract tests for the durable merge plan (tasks 1.1 and 1.3)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from merge_plan import MergePlanValidationError, validate_plan  # noqa: E402


def _state(**overrides: object) -> dict:
    state = {
        "outcome": "pending",
        "needs_revalidation": False,
        "claimed_by": None,
        "staleness": "fresh",
        "ci_state": "clean",
        "ci_failure_class": None,
        "unresolved_comments": 0,
        "unresolved_comment_summary": None,
        "vendor_verdict": None,
        "iterate_consensus_path": None,
        "blocking_reason": None,
    }
    state.update(overrides)
    return state


def valid_plan() -> dict:
    return {
        "schema_version": "1.1",
        "generated_at": "2026-08-19T12:00:00+00:00",
        "storage_tier": "file",
        "base_branch": "main",
        "approved_at": None,
        "last_merged_pr": None,
        "compact_requested": False,
        "nodes": [
            {
                "pr": 10,
                "title": "First",
                "origin": "openspec",
                "strategy": "rebase",
                "auto_executable": False,
                "definition": {
                    "depends_on": [],
                    "gates": ["proposal_acceptance"],
                    "changed_files": ["src/a.py"],
                    "kind": "implementation",
                    "change_id": "first",
                    "remediation_skill": "iterate-on-implementation",
                    "kind_overridden": False,
                },
                "state": _state(),
            },
            {
                "pr": 11,
                "title": "Second",
                "origin": "dependabot",
                "strategy": "squash",
                "auto_executable": True,
                "definition": {
                    "depends_on": [10],
                    "gates": [],
                    "changed_files": ["src/a.py"],
                    "kind": "automation",
                    "change_id": None,
                    "remediation_skill": "none",
                    "kind_overridden": False,
                },
                "state": _state(),
            },
        ],
    }


def test_plan_validates_against_shipped_contract() -> None:
    validate_plan(valid_plan())


def test_schema_1_0_documents_are_rejected() -> None:
    plan = valid_plan()
    plan["schema_version"] = "1.0"

    with pytest.raises(MergePlanValidationError, match="1.1"):
        validate_plan(plan)


def test_kind_fields_round_trip_on_valid_plan() -> None:
    plan = valid_plan()
    validate_plan(plan)
    assert plan["nodes"][0]["definition"]["kind"] == "implementation"
    assert plan["nodes"][0]["definition"]["remediation_skill"] == (
        "iterate-on-implementation"
    )
    assert plan["nodes"][1]["definition"]["kind"] == "automation"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda plan: plan["nodes"].append(copy.deepcopy(plan["nodes"][0])), "duplicate PR"),
        (lambda plan: plan["nodes"][1]["definition"]["depends_on"].append(99), "unknown PR"),
        (lambda plan: plan["nodes"][0]["definition"]["depends_on"].append(10), "depend on itself"),
        (lambda plan: plan["nodes"][0]["definition"]["depends_on"].append(11), "cycle"),
    ],
)
def test_plan_rejects_semantically_invalid_dags(mutate, message: str) -> None:
    plan = valid_plan()
    mutate(plan)

    with pytest.raises(MergePlanValidationError, match=message):
        validate_plan(plan)


def test_plan_requires_analysis_state_on_every_node() -> None:
    plan = valid_plan()
    del plan["nodes"][0]["state"]["ci_state"]

    with pytest.raises(MergePlanValidationError, match="ci_state"):
        validate_plan(plan)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda plan: plan["nodes"][0].update(auto_executable=True),
            "OpenSpec",
        ),
        (
            lambda plan: plan["nodes"][0]["definition"].update(gates=[]),
            "proposal_acceptance",
        ),
        (
            lambda plan: plan["nodes"][1]["definition"].update(
                gates=["required_review"],
            ),
            "auto-executable",
        ),
        (
            lambda plan: (
                plan["nodes"][1].update(auto_executable=False),
                plan["nodes"][1]["definition"].update(gates=[]),
            ),
            "non-auto-executable",
        ),
    ],
)
def test_plan_rejects_gate_and_auto_execution_contradictions(
    mutate,
    message: str,
) -> None:
    plan = valid_plan()
    mutate(plan)

    with pytest.raises(MergePlanValidationError, match=message):
        validate_plan(plan)
