"""Behavior tests for plan-driven single-PR execution (tasks 4.1-4.4)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

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
        "guard_sync_point": lambda _root: {"allowed": True},
        "get_live_status": lambda _pr: passing_status(),
        "check_staleness": lambda _pr, _origin: {
            "staleness": "fresh",
            "ci_merge_base_stale": False,
        },
        "refresh_branch": lambda _pr: {"success": True},
        "analyze_comments": lambda _pr: {
            "unresolved_count": 0,
            "unresolved_threads": [],
        },
        "review_vendor": lambda _pr, _origin, _comments: {
            "eligibility": {"eligible": True, "reason": "needs_review"},
            "dispatched": True,
            "vendors": [{"success": True, "vendor": "reviewer"}],
            "error": None,
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
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)

    result = execute_node(path, 11, dependencies=dependencies(), claim_id="run-1")

    updated = FilePlanStore(path).load()
    states = {node["pr"]: node["state"] for node in updated["nodes"]}
    assert result["outcome"] == "merged"
    assert states[11]["outcome"] == "merged"
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
    assert "proposal_acceptance" in result["gates"]


def test_openspec_gate_cannot_be_bypassed_by_generic_approval(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path)

    result = execute_node(
        path,
        10,
        approve_gate=True,
        dependencies=dependencies(),
    )

    assert result["action"] == "human_gate"
    assert result["outcome"] == "pending"
    assert result["override_allowed"] is False


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


def test_mirror_invocation_resolves_repository_canonical_skill_tree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    canonical = repo / "skills" / "merge-pull-requests" / "scripts"
    mirror = repo / ".agents" / "skills" / "merge-pull-requests" / "scripts"
    canonical.mkdir(parents=True)
    mirror.mkdir(parents=True)
    (repo / ".git").write_text("gitdir: elsewhere", encoding="utf-8")

    resolved = canonical_scripts_dir(mirror / "execute_plan.py")

    assert resolved == canonical


def test_sync_point_guard_blocks_before_live_checks_or_merge(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)
    calls: list[str] = []

    result = execute_node(
        path,
        11,
        dependencies=dependencies(
            guard_sync_point=lambda _root: {
                "allowed": False,
                "reason": "active agents hold worktrees",
            },
            get_live_status=lambda _pr: calls.append("live") or passing_status(),
            merge=lambda _pr, _strategy: calls.append("merge") or {"success": True},
        ),
    )

    assert result["action"] == "sync_point_blocked"
    assert calls == []


def test_each_execution_recomputes_live_staleness_before_refresh(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)
    calls = {"staleness": 0, "refresh": 0}

    def stale(_pr: int, _origin: str) -> dict:
        calls["staleness"] += 1
        return {
            "staleness": "stale" if calls["staleness"] == 1 else "fresh",
            "ci_merge_base_stale": calls["staleness"] == 1,
        }

    result = execute_node(
        path,
        11,
        claim_id="run-stale",
        dependencies=dependencies(
            check_staleness=stale,
            refresh_branch=lambda _pr: calls.__setitem__("refresh", 1) or {"success": True},
        ),
    )

    assert result["action"] == "merged"
    assert calls == {"staleness": 2, "refresh": 1}


def test_refresh_accepts_historical_overlap_when_merge_base_and_ci_are_fresh(
    tmp_path: Path,
) -> None:
    """Historical overlap remains stale even after a successful branch refresh."""

    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)
    calls = {"staleness": 0, "refresh": 0, "merge": 0}

    def overlap_classifier(_pr: int, _origin: str) -> dict:
        calls["staleness"] += 1
        return {
            "staleness": "stale",
            "ci_merge_base_stale": calls["staleness"] == 1,
            "overlapping_files": ["skills/example.py"],
        }

    result = execute_node(
        path,
        11,
        claim_id="overlap-refresh",
        dependencies=dependencies(
            check_staleness=overlap_classifier,
            refresh_branch=lambda _pr: calls.__setitem__("refresh", 1) or {"success": True},
            merge=lambda _pr, _strategy: (
                calls.__setitem__("merge", 1) or {"success": True, "status": "merged"}
            ),
        ),
    )

    assert result["action"] == "merged"
    assert calls == {"staleness": 2, "refresh": 1, "merge": 1}


def test_refresh_blocks_until_current_merge_base_and_fresh_ci(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)
    statuses = iter(
        [
            passing_status(),
            passing_status(checks_pending=True, checks_passing=False, can_merge=False),
        ]
    )

    result = execute_node(
        path,
        11,
        dependencies=dependencies(
            get_live_status=lambda _pr: next(statuses),
            check_staleness=lambda _pr, _origin: {
                "staleness": "stale",
                "ci_merge_base_stale": False,
            },
        ),
    )

    assert result["action"] == "revalidation_failed"
    assert "CI" in result["reason"]


def test_claim_is_persisted_before_refresh_review_and_merge(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    plan["nodes"][1]["state"]["needs_revalidation"] = True
    path = persisted_plan(tmp_path, plan)

    def assert_claimed(_pr: int) -> dict:
        state = FilePlanStore(path).load()["nodes"][1]["state"]
        assert state["outcome"] == "in_progress"
        assert state["claimed_by"] == "run-claim"
        return {"success": True}

    execute_node(
        path,
        11,
        claim_id="run-claim",
        dependencies=dependencies(refresh_branch=assert_claimed),
    )


def test_replay_of_open_in_progress_claim_is_rejected(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    plan["nodes"][1]["state"].update(outcome="in_progress", claimed_by="old-run")
    path = persisted_plan(tmp_path, plan)
    calls: list[str] = []

    result = execute_node(
        path,
        11,
        claim_id="new-run",
        dependencies=dependencies(
            review_vendor=lambda *_args: calls.append("review") or {},
            merge=lambda *_args: calls.append("merge") or {},
        ),
    )

    assert result["action"] == "execution_in_progress"
    assert result["claimed_by"] == "old-run"
    assert calls == []


def test_retry_reconciles_merged_live_state_without_merging_again(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    plan["nodes"][1]["state"].update(outcome="in_progress", claimed_by="old-run")
    path = persisted_plan(tmp_path, plan)
    calls: list[str] = []

    result = execute_node(
        path,
        11,
        claim_id="new-run",
        dependencies=dependencies(
            get_live_status=lambda _pr: passing_status(state="MERGED", merged=True),
            merge=lambda *_args: calls.append("merge") or {},
        ),
    )

    assert result["action"] == "reconciled"
    assert result["outcome"] == "merged"
    assert calls == []
    assert FilePlanStore(path).load()["nodes"][1]["state"]["claimed_by"] is None


def test_retry_reconciles_before_prerequisites_human_gate_and_sync_guard(
    tmp_path: Path,
) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"].update(outcome="in_progress", claimed_by="old-run")
    path = persisted_plan(tmp_path, plan)

    result = execute_node(
        path,
        10,
        claim_id="retry-run",
        dependencies=dependencies(
            get_live_status=lambda _pr: passing_status(state="MERGED", merged=True),
            guard_sync_point=lambda _root: pytest.fail(
                "terminal reconciliation must precede the sync guard"
            ),
        ),
    )

    assert result["action"] == "reconciled"
    assert result["outcome"] == "merged"


def test_crash_after_remote_merge_is_reconciled_on_retry(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)

    def crash_after_merge(_pr: int, _strategy: str) -> dict:
        raise RuntimeError("process crashed after GitHub accepted merge")

    with pytest.raises(RuntimeError, match="process crashed"):
        execute_node(
            path,
            11,
            claim_id="crashed-run",
            dependencies=dependencies(merge=crash_after_merge),
        )
    assert FilePlanStore(path).load()["nodes"][1]["state"]["outcome"] == "in_progress"

    result = execute_node(
        path,
        11,
        claim_id="retry-run",
        dependencies=dependencies(
            get_live_status=lambda _pr: passing_status(state="MERGED", merged=True),
        ),
    )
    assert result["action"] == "reconciled"


def test_vendor_review_eligible_without_verdict_blocks(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)

    result = execute_node(
        path,
        11,
        dependencies=dependencies(
            review_vendor=lambda *_args: {
                "eligibility": {"eligible": True, "reason": "needs_review"},
                "dispatched": False,
                "vendors": [],
                "consensus": None,
                "error": "review vendor unavailable",
            },
        ),
    )

    assert result["action"] == "vendor_review_gate"
    assert "unavailable" in result["reason"]
    assert result["outcome"] == "pending"


def test_final_save_failure_leaves_reconcilable_in_progress_claim(
    tmp_path: Path,
) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)

    class FailFinalSaveStore(FilePlanStore):
        def __init__(self, plan_path: Path) -> None:
            super().__init__(plan_path)
            self.saves = 0

        def save(self, pending: dict) -> None:
            self.saves += 1
            if self.saves == 2:
                raise OSError("final plan save failed")
            super().save(pending)

    merge_calls: list[int] = []
    with pytest.raises(OSError, match="final plan save failed"):
        execute_node(
            path,
            11,
            claim_id="save-failure-run",
            store=FailFinalSaveStore(path),
            dependencies=dependencies(
                merge=lambda pr, _strategy: (
                    merge_calls.append(pr) or {"success": True, "status": "merged"}
                ),
            ),
        )

    persisted = FilePlanStore(path).load()["nodes"][1]["state"]
    assert persisted["outcome"] == "in_progress"
    assert persisted["claimed_by"] == "save-failure-run"
    assert merge_calls == [11]

    result = execute_node(
        path,
        11,
        claim_id="reconcile-save-failure",
        dependencies=dependencies(
            get_live_status=lambda _pr: passing_status(state="MERGED", merged=True),
            merge=lambda *_args: pytest.fail("reconciliation must not merge again"),
        ),
    )
    assert result["action"] == "reconciled"
