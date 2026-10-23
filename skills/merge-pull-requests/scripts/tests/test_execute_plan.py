"""Behavior tests for plan-driven single-PR execution (tasks 4.1-4.4)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import execute_plan  # noqa: E402
from execute_plan import (  # noqa: E402
    ExecutionDependencies,
    canonical_scripts_dir,
    execute_node,
)
from plan_storage import FilePlanStore  # noqa: E402
from test_merge_plan_contract import valid_plan  # noqa: E402
from verdict_binding import bind, patch_id_from_diff  # noqa: E402

HEAD = "c" * 40
MOVED = "e" * 40
DIFF = (
    "diff --git a/x.txt b/x.txt\n"
    "index 0000000..1111111 100644\n"
    "--- a/x.txt\n"
    "+++ b/x.txt\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)
HUMAN = {"login": "human", "vendor": None, "session_id": None}


def clean_review() -> dict:
    return {
        "eligibility": {"eligible": True, "reason": "needs_review"},
        "dispatched": True,
        "vendors": [{"success": True, "vendor": "codex", "agent_id": "codex-local"}],
        "error": None,
        "consensus": {"summary": {"blocking_count": 0}},
    }


def passing_status(**overrides) -> dict:
    status = {
        "branch": "dependabot/pip/example-2",
        "mergeable": "MERGEABLE",
        "checks_failed": False,
        "checks_pending": False,
        "checks_passing": True,
        "check_details": [{"name": "tests", "state": "SUCCESS"}],
        "can_merge": True,
        "head_sha": HEAD,
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
        "review_vendor": lambda _pr, _origin, _comments, _author: clean_review(),
        "merge": lambda _pr, _strategy, _head, _waiver: {"success": True, "status": "merged"},
        "pr_diff": lambda _pr: DIFF,
        "pr_author": lambda _pr: dict(HUMAN),
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
    assert result["delegation"][0].startswith("/quick-task")
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
            merge=lambda *_args: calls.append("merge") or {"success": True},
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
            merge=lambda *_args: (
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

    def crash_after_merge(_pr: int, _strategy: str, *_rest) -> dict:
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
    node = plan["nodes"][1]
    node["origin"] = "other"
    node["auto_executable"] = False
    node["definition"]["kind"] = "implementation"
    node["definition"]["remediation_skill"] = "quick-task"
    node["definition"]["gates"] = ["required_review"]
    path = persisted_plan(tmp_path, plan)

    result = execute_node(
        path,
        11,
        approve_gate=True,
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

        def _save_locked(self, pending: dict) -> None:
            self.saves += 1
            if self.saves == 2:
                raise OSError("final plan save failed")
            super()._save_locked(pending)

    merge_calls: list[int] = []
    with pytest.raises(OSError, match="final plan save failed"):
        execute_node(
            path,
            11,
            claim_id="save-failure-run",
            store=FailFinalSaveStore(path),
            dependencies=dependencies(
                merge=lambda pr, *_rest: (
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


def test_plan_kind_delegation_uses_iterate_on_plan() -> None:
    from execute_plan import _delegation_commands

    node = valid_plan()["nodes"][0]
    node["definition"]["kind"] = "plan"
    node["definition"]["remediation_skill"] = "iterate-on-plan"
    node["definition"]["change_id"] = "add-widget"
    commands = _delegation_commands(node, "openspec/add-widget")
    assert commands == ["/iterate-on-plan add-widget --vendor-review"]


def test_implementation_kind_delegation_uses_iterate_on_implementation() -> None:
    from execute_plan import _delegation_commands

    node = valid_plan()["nodes"][0]
    commands = _delegation_commands(node, "openspec/first")
    assert commands == ["/iterate-on-implementation first --vendor-review"]


def test_cheap_path_skips_vendor_review_and_records_a_policy_waiver(tmp_path: Path) -> None:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    path = persisted_plan(tmp_path, plan)
    merges: list[tuple] = []

    result = execute_node(
        path,
        11,
        dependencies=dependencies(
            review_vendor=lambda pr, *_rest: pytest.fail(
                "cheap-path must not dispatch vendor review"
            ),
            pr_author=lambda _pr: pytest.fail("cheap-path needs no author lookup"),
            merge=lambda *args: merges.append(args) or {"success": True},
        ),
    )
    assert result["outcome"] == "merged"
    loaded = FilePlanStore(path).load()
    assert loaded["last_merged_pr"] == 11
    assert loaded["compact_requested"] is True
    waiver = loaded["nodes"][1]["state"]["review_waiver"]
    assert waiver["source"] == "policy"
    assert waiver["eligibility_reason"] == "automation_cheap_path"
    assert result["vendor_review"]["review_waiver"] == waiver
    assert merges == [(11, "squash", HEAD, waiver)]


def _gated_implementation_plan(stored_verdict: dict | None = None) -> dict:
    plan = valid_plan()
    plan["nodes"][0]["state"]["outcome"] = "merged"
    node = plan["nodes"][1]
    node["origin"] = "other"
    node["auto_executable"] = False
    node["definition"]["kind"] = "implementation"
    node["definition"]["remediation_skill"] = "iterate-on-implementation"
    node["definition"]["change_id"] = "first"
    node["definition"]["gates"] = ["required_review"]
    if stored_verdict is not None:
        node["state"]["vendor_verdict"] = stored_verdict
    return plan


def _stored(head_sha: str, patch_id: str | None) -> dict:
    return bind(clean_review(), head_sha=head_sha, patch_id=patch_id, author=HUMAN)


def test_current_stored_verdict_skips_vendor_review(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan(_stored(HEAD, None)))

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            review_vendor=lambda pr, *_rest: pytest.fail(
                "a current verdict must skip vendor_review.py"
            ),
            pr_diff=lambda _pr: pytest.fail("a current head needs no patch-id"),
        ),
    )
    assert result["outcome"] == "merged"
    assert result["vendor_review"]["reused_stored_verdict"] is True
    assert result["vendor_review"]["binding"]["head_sha"] == HEAD


def test_rebased_stored_verdict_skips_vendor_review(tmp_path: Path) -> None:
    stored = _stored(MOVED, patch_id_from_diff(DIFF))
    path = persisted_plan(tmp_path, _gated_implementation_plan(stored))

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            review_vendor=lambda pr, *_rest: pytest.fail(
                "a rebased verdict must skip vendor_review.py"
            ),
        ),
    )
    assert result["outcome"] == "merged"
    assert result["vendor_review"]["reused_stored_verdict"] is True


def test_stale_stored_verdict_is_superseded_by_a_fresh_bound_review(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan(_stored(MOVED, "0" * 40)))
    dispatched: list[int] = []

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            review_vendor=lambda pr, *_rest: dispatched.append(pr) or clean_review(),
        ),
    )
    assert dispatched == [11]
    assert result["outcome"] == "merged"
    evidence = result["vendor_review"]
    assert evidence["superseded_verdict"] == f"stale verdict: reviewed {MOVED[:7]}, live {HEAD[:7]}"
    assert evidence["binding"]["head_sha"] == HEAD
    assert evidence["binding"]["patch_id"] == patch_id_from_diff(DIFF)
    stored = FilePlanStore(path).load()["nodes"][1]["state"]["vendor_verdict"]
    assert stored["binding"]["head_sha"] == HEAD


def test_stored_verdict_with_blocking_findings_is_not_reused(tmp_path: Path) -> None:
    stored = _stored(HEAD, None)
    stored["consensus"] = {"summary": {"blocking_count": 2}}
    path = persisted_plan(tmp_path, _gated_implementation_plan(stored))
    dispatched: list[int] = []

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            review_vendor=lambda pr, *_rest: dispatched.append(pr) or clean_review(),
        ),
    )
    assert dispatched == [11]
    assert result["outcome"] == "merged"


def test_every_stored_review_is_bound_to_the_live_head(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())
    authors: list[dict] = []
    author = {"login": "bot", "vendor": "codex", "session_id": "s-1"}

    execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            pr_author=lambda _pr: dict(author),
            review_vendor=lambda _pr, _origin, _comments, who: (
                authors.append(who) or clean_review()
            ),
        ),
    )
    assert authors == [author]
    binding = FilePlanStore(path).load()["nodes"][1]["state"]["vendor_verdict"]["binding"]
    assert binding["head_sha"] == HEAD
    assert binding["author"] == author


def test_small_pr_ineligibility_records_a_policy_waiver(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            review_vendor=lambda *_args: {
                "eligibility": {"eligible": False, "reason": "small_pr"},
                "consensus": None,
            },
        ),
    )
    assert result["outcome"] == "merged"
    waiver = FilePlanStore(path).load()["nodes"][1]["state"]["review_waiver"]
    assert waiver["source"] == "policy"
    assert waiver["eligibility_reason"] == "small_pr"
    assert result["vendor_review"]["review_waiver"] == waiver


@pytest.mark.parametrize("reason", ["draft_pr", "changes_requested", "something_new"])
def test_unwaivable_ineligibility_blocks(tmp_path: Path, reason: str) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            review_vendor=lambda *_args: {
                "eligibility": {"eligible": False, "reason": reason},
                "consensus": None,
            },
            merge=lambda *_args: pytest.fail("an unwaived ineligible review must not merge"),
        ),
    )
    assert result["action"] == "vendor_review_gate"
    assert result["outcome"] == "pending"
    state = FilePlanStore(path).load()["nodes"][1]["state"]
    assert state["review_waiver"] is None


def test_head_mismatch_merge_failure_stays_pending(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            merge=lambda *_args: {"success": False, "head_mismatch": True, "error": "modified"},
        ),
    )
    assert result["action"] == "merge_failed"
    assert result["outcome"] == "pending"
    assert "head mismatch" in result["reason"]
    assert FilePlanStore(path).load()["nodes"][1]["state"]["outcome"] == "pending"


def test_unknown_pr_author_blocks_before_review(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())

    def no_author(_pr: int) -> dict:
        raise RuntimeError("gh pr view failed")

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            pr_author=no_author,
            review_vendor=lambda *_args: pytest.fail("review needs a known author"),
        ),
    )
    assert result["outcome"] == "pending"
    assert "author could not be determined" in result["reason"]


def test_missing_live_head_blocks(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())

    result = execute_node(
        path,
        11,
        approve_gate=True,
        dependencies=dependencies(
            get_live_status=lambda _pr: passing_status(head_sha=None),
            merge=lambda *_args: pytest.fail("an unpinnable merge must not run"),
        ),
    )
    assert result["outcome"] == "pending"
    assert "head SHA" in result["reason"]


# --- --waive-review (operator waiver) ----------------------------------------


def _failing_dependencies() -> ExecutionDependencies:
    def fail(*_args):
        pytest.fail("a rejected waiver must not touch any dependency")

    return ExecutionDependencies(
        guard_sync_point=fail, get_live_status=fail, check_staleness=fail,
        refresh_branch=fail, analyze_comments=fail, review_vendor=fail,
        merge=fail, pr_diff=fail, pr_author=fail,
    )


@pytest.mark.parametrize("reason", ["", "   "])
def test_blank_waive_review_exits_2_before_any_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str,
) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(execute_plan, "DEFAULT_DEPENDENCIES", _failing_dependencies())
    monkeypatch.setattr(
        sys, "argv",
        ["execute_plan.py", "--execute", str(path), "--pr", "11", "--approve-gate",
         "--waive-review", reason],
    )

    with pytest.raises(SystemExit) as exit_info:
        execute_plan.main()

    assert exit_info.value.code == 2
    assert path.read_text(encoding="utf-8") == before


def test_waive_review_records_operator_waiver_and_merges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())
    merges: list[tuple] = []
    monkeypatch.setenv("USER", "jan")
    monkeypatch.setattr(
        execute_plan,
        "DEFAULT_DEPENDENCIES",
        dependencies(
            review_vendor=lambda *_args: {
                "eligibility": {"eligible": True, "reason": "needs_review"},
                "dispatched": False,
                "vendors": [],
                "consensus": None,
                "error": "review vendor unavailable",
            },
            merge=lambda *args: merges.append(args) or {"success": True},
        ),
    )
    monkeypatch.setattr(
        sys, "argv",
        ["execute_plan.py", "--execute", str(path), "--pr", "11", "--approve-gate",
         "--waive-review", "hotfix approved in incident channel"],
    )

    assert execute_plan.main() == 0

    waiver = FilePlanStore(path).load()["nodes"][1]["state"]["review_waiver"]
    assert waiver["source"] == "operator"
    assert waiver["reason"] == "hotfix approved in incident channel"
    assert waiver["approver"] == "jan"
    printed = json.loads(capsys.readouterr().out)
    assert printed["vendor_review"]["review_waiver"] == waiver
    assert merges == [(11, "squash", HEAD, waiver)]


def test_operator_waiver_does_not_override_change_requests(tmp_path: Path) -> None:
    path = persisted_plan(tmp_path, _gated_implementation_plan())

    result = execute_node(
        path,
        11,
        approve_gate=True,
        waive_review="ship it",
        waiver_approver="jan",
        dependencies=dependencies(
            review_vendor=lambda *_args: {
                "eligibility": {"eligible": False, "reason": "changes_requested"},
                "consensus": None,
            },
            merge=lambda *_args: pytest.fail("change requests must block"),
        ),
    )
    assert result["action"] == "vendor_review_gate"
    assert "change requests" in result["reason"]


def test_execute_plan_source_does_not_checkout_or_commit_pr_branch() -> None:
    source = (Path(__file__).resolve().parent.parent / "execute_plan.py").read_text(
        encoding="utf-8"
    )
    assert "git checkout" not in source
    assert "git commit" not in source
    assert "git push" not in source


def test_proposal_accepted_allows_openspec_merge_after_dedicated_workflow(
    tmp_path: Path,
) -> None:
    path = persisted_plan(tmp_path)
    result = execute_node(
        path,
        10,
        proposal_accepted=True,
        dependencies=dependencies(),
    )
    assert result["outcome"] == "merged"
