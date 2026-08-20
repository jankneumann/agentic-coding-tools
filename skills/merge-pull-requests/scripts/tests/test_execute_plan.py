"""Behavior tests for plan-driven single-PR execution (tasks 4.1-4.4)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from execute_plan import (  # noqa: E402
    ExecutionDependencies,
    canonical_scripts_dir,
    execute_node,
)
from plan_storage import FilePlanStore  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402


def passing_status(**overrides) -> dict:
    status = {
        "branch": "dependabot/pip/example-2",
        "mergeable": "MERGEABLE",
        "checks_failed": False,
        "checks_pending": False,
        "checks_passing": True,
        "check_details": [{"name": "tests", "state": "SUCCESS"}],
        "can_merge": True,
    }
    status.update(overrides)
    return status


def dependencies(**overrides) -> ExecutionDependencies:
    values = {
        "get_live_status": lambda _pr: passing_status(),
        "refresh_branch": lambda _pr: {"success": True},
        "analyze_comments": lambda _pr: {
            "unresolved_count": 0,
            "unresolved_threads": [],
        },
        "review_vendor": lambda _pr, _origin, _comments: {
            "consensus": {"summary": {"blocking_count": 0}},
        },
        "merge": lambda _pr, _strategy: {"success": True, "status": "merged"},
    }
    values.update(overrides)
    return ExecutionDependencies(**values)


def persisted_plan(tmp_path: Path, plan: dict | None = None) -> Path:
    path = tmp_path / "merge-plan.json"
    FilePlanStore(path).save(plan or valid_plan())
    return path


def test_successful_execution_updates_outcome_and_flags_transitive_downstream(
    tmp_path: Path,
) -> None:
    plan = valid_plan()
    third = copy.deepcopy(plan["nodes"][1])
    third["pr"] = 12
    third["title"] = "Third"
    third["definition"]["depends_on"] = [11]
    plan["nodes"].append(third)
    path = persisted_plan(tmp_path, plan)

    result = execute_node(path, 10, approve_gate=True, dependencies=dependencies())

    updated = FilePlanStore(path).load()
    states = {node["pr"]: node["state"] for node in updated["nodes"]}
    assert result["outcome"] == "merged"
    assert states[10]["outcome"] == "merged"
    assert states[11]["needs_revalidation"] is True
    assert states[12]["needs_revalidation"] is True


def test_flagged_node_refreshes_and_rechecks_live_state_before_merge(
    tmp_path: Path,
) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    plan["nodes"][1]["state"]["needs_revalidation"] = True
    path = persisted_plan(tmp_path, plan)
    calls = {"status": 0, "refresh": 0}

    def live(_pr: int) -> dict:
        calls["status"] += 1
        return passing_status()

    def refresh(_pr: int) -> dict:
        calls["refresh"] += 1
        return {"success": True}

    result = execute_node(
        path,
        11,
        dependencies=dependencies(get_live_status=live, refresh_branch=refresh),
    )

    assert result["outcome"] == "merged"
    assert calls == {"status": 2, "refresh": 1}
    node = FilePlanStore(path).load()["nodes"][1]
    assert node["state"]["needs_revalidation"] is False


def test_human_gate_halts_without_explicit_approval(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path)

    result = execute_node(path, 10, dependencies=dependencies())

    assert result["outcome"] == "pending"
    assert result["action"] == "human_gate"
    assert "proposal_acceptance" not in result["gates"]
    assert "requires_human_approval" in result["gates"]


def test_failing_security_check_preserves_pending_outcome(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)
    status = passing_status(
        checks_failed=True,
        checks_passing=False,
        can_merge=False,
        check_details=[{"name": "CodeQL security", "state": "FAILURE"}],
    )

    result = execute_node(
        path,
        11,
        dependencies=dependencies(get_live_status=lambda _pr: status),
    )

    assert result["action"] == "security_gate"
    assert result["outcome"] == "pending"
    node = FilePlanStore(path).load()["nodes"][1]
    assert "CodeQL security" in node["state"]["blocking_reason"]


def test_unresolved_comments_persist_summary_and_return_delegation(
    tmp_path: Path,
) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)
    comments = {
        "unresolved_count": 2,
        "unresolved_threads": [
            {"file": "src/a.py", "first_comment": "Handle the empty case"},
            {"file": "src/b.py", "first_comment": "Add a regression test"},
        ],
    }

    result = execute_node(
        path,
        11,
        dependencies=dependencies(analyze_comments=lambda _pr: comments),
    )

    assert result["action"] == "delegate_comments"
    assert "iterate-on-implementation" in result["delegation"][0]
    assert "quick-task" in result["delegation"][1]
    node = FilePlanStore(path).load()["nodes"][1]
    assert node["state"]["unresolved_comments"] == 2
    assert "src/a.py" in node["state"]["unresolved_comment_summary"]


def test_executor_resolves_helpers_from_canonical_skill_tree() -> None:
    resolved = canonical_scripts_dir()
    assert resolved.parts[-3:] == ("skills", "merge-pull-requests", "scripts")
    assert ".claude" not in resolved.parts
    assert ".agents" not in resolved.parts
