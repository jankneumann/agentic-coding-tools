"""Tests for the read-only next-ready-node helper."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from next_node import next_ready_pr  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402


def test_next_ready_is_first_pending_with_merged_deps() -> None:
    plan = valid_plan()
    assert next_ready_pr(plan) == 10
    plan["nodes"][0]["state"]["outcome"] = "merged"
    assert next_ready_pr(plan, after=10) == 11


def test_blocked_pending_node_is_not_ready() -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "pending"
    plan["nodes"][1]["state"]["outcome"] = "pending"
    assert next_ready_pr(plan) == 10


def test_no_ready_node_when_all_merged() -> None:
    plan = valid_plan()
    for node in plan["nodes"]:
        node["state"]["outcome"] = "merged"
    assert next_ready_pr(plan) is None
