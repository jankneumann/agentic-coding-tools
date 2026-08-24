"""Tests for the faithful Markdown projection (tasks 2.1 and 2.2)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_plan import render_plan  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402


def test_render_plan_includes_every_node_outcome_and_dependency_edge() -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"

    rendered = render_plan(plan)

    assert "| #10 | First | openspec | merged |" in rendered
    assert "| #11 | Second | dependabot | pending |" in rendered
    assert "#11 → #10" in rendered


def test_render_plan_does_not_mutate_authoritative_json() -> None:
    plan = valid_plan()
    before = copy.deepcopy(plan)

    render_plan(plan)

    assert plan == before


def test_render_plan_preserves_live_blocking_ci_staleness_and_comment_state() -> None:
    plan = valid_plan()
    state = plan["nodes"][1]["state"]
    state["ci_state"] = "blocked"
    state["staleness"] = "stale"
    state["unresolved_comments"] = 2
    state["unresolved_comment_summary"] = "src/a.py: fix edge case"
    state["blocking_reason"] = "security scan failed"

    rendered = render_plan(plan)

    assert "blocked" in rendered
    assert "stale" in rendered
    assert "2" in rendered
    assert "security scan failed" in rendered
    assert "src/a.py: fix edge case" in rendered
