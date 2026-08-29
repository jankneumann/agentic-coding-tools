"""Tests for living-plan prerequisite amendment (tasks 5.1 and 5.2)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from merge_plan import MergePlanValidationError, amend_plan  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402


def prerequisite_node() -> dict:
    node = copy.deepcopy(valid_plan()["nodes"][1])
    node["pr"] = 99
    node["title"] = "Security prerequisite"
    node["origin"] = "sentinel"
    node["definition"]["depends_on"] = []
    node["definition"]["changed_files"] = ["requirements.lock"]
    return node


def test_amend_plan_appends_prerequisite_and_blocks_every_affected_node() -> None:
    original = valid_plan()

    amended = amend_plan(
        original,
        prerequisite_node(),
        affected_prs=[10, 11],
        reason="Required security upgrade",
    )

    assert [node["pr"] for node in original["nodes"]] == [10, 11]
    assert [node["pr"] for node in amended["nodes"]] == [10, 11, 99]
    nodes = {node["pr"]: node for node in amended["nodes"]}
    assert nodes[99]["definition"]["inserted_reason"] == "Required security upgrade"
    assert 99 in nodes[10]["definition"]["depends_on"]
    assert 99 in nodes[11]["definition"]["depends_on"]


def test_amend_plan_rejects_duplicate_pr_without_removing_existing_nodes() -> None:
    duplicate = prerequisite_node()
    duplicate["pr"] = 10

    with pytest.raises(MergePlanValidationError, match="already exists"):
        amend_plan(
            valid_plan(),
            duplicate,
            affected_prs=[11],
            reason="Duplicate",
        )
