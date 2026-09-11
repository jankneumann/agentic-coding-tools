"""Tests for iterate-skill pairing preconditions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from iterate_preconditions import iterate_precondition_error  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402


def test_approved_plan_node_is_illegal_for_iterate_on_plan() -> None:
    node = valid_plan()["nodes"][0]
    node["definition"]["kind"] = "plan"
    node["definition"]["remediation_skill"] = "iterate-on-plan"
    assert iterate_precondition_error(node, proposal_approved=True)


def test_unapproved_implementation_node_is_illegal() -> None:
    node = valid_plan()["nodes"][0]
    assert iterate_precondition_error(node, proposal_approved=False)


def test_matching_preconditions_pass() -> None:
    plan_node = valid_plan()["nodes"][0]
    plan_node["definition"]["kind"] = "plan"
    plan_node["definition"]["remediation_skill"] = "iterate-on-plan"
    assert iterate_precondition_error(plan_node, proposal_approved=False) is None
    impl = valid_plan()["nodes"][0]
    assert iterate_precondition_error(impl, proposal_approved=True) is None
