"""Accepted merge requests must not release dependent PRs before integration."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
for path in (SCRIPTS, SCRIPTS / "tests"):
    sys.path.insert(0, str(path))

from execute_plan import execute_node  # noqa: E402
from plan_storage import FilePlanStore  # noqa: E402
from test_execute_plan import dependencies, passing_status, persisted_plan  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402


def ready_plan(tmp_path: Path) -> Path:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    child = copy.deepcopy(plan["nodes"][1])
    child["pr"] = 12
    child["definition"]["depends_on"] = [11]
    plan["nodes"].append(child)
    return persisted_plan(tmp_path, plan)


@pytest.mark.parametrize("status", ["enqueued", "speculating", "unexpected", None])
def test_acceptance_is_nonterminal_and_does_not_release_dependents(tmp_path, status):
    path = ready_plan(tmp_path)
    result = execute_node(
        path, 11, claim_id="request-1",
        dependencies=dependencies(merge=lambda *_: {"success": True, "status": status}),
    )
    assert result["outcome"] == "in_progress"
    assert result["action"] == "awaiting_merge_confirmation"
    plan = FilePlanStore(path).load()
    assert plan["nodes"][1]["state"]["awaiting_merge_confirmation"] is True
    assert plan["nodes"][2]["state"]["needs_revalidation"] is False
    assert plan["last_merged_pr"] is None
    assert plan["compact_requested"] is False
    assert execute_node(path, 12, dependencies=dependencies())["action"] == "blocked"


@pytest.mark.parametrize("claim_id", ["request-1", "restarted-worker"])
def test_waiting_request_is_not_resubmitted_even_by_same_claim(tmp_path, claim_id):
    path = ready_plan(tmp_path)
    execute_node(path, 11, claim_id="request-1", dependencies=dependencies(
        merge=lambda *_: {"success": True, "status": "enqueued"},
    ))
    result = execute_node(path, 11, claim_id=claim_id, dependencies=dependencies(
        merge=lambda *_: pytest.fail("must not submit another merge request"),
    ))
    assert result["action"] == "awaiting_merge_confirmation"
    assert result["outcome"] == "in_progress"


@pytest.mark.parametrize("remote_state, outcome", [("MERGED", "merged"), ("CLOSED", "closed")])
def test_restart_reconciles_actual_remote_outcome(tmp_path, remote_state, outcome):
    path = ready_plan(tmp_path)
    execute_node(path, 11, claim_id="request-1", dependencies=dependencies(
        merge=lambda *_: {"success": True, "status": "enqueued"},
    ))
    result = execute_node(path, 11, claim_id="restarted-worker", dependencies=dependencies(
        get_live_status=lambda _: passing_status(state=remote_state),
        merge=lambda *_: pytest.fail("must reconcile without submitting"),
    ))
    assert result["outcome"] == outcome
    plan = FilePlanStore(path).load()
    state = plan["nodes"][1]["state"]
    assert state["claimed_by"] is None
    assert state.get("awaiting_merge_confirmation", False) is False
    assert plan["nodes"][2]["state"]["needs_revalidation"] is (outcome == "merged")
