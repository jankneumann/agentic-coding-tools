"""Content invariants for the merge-pull-requests skill."""
import re
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests"

_HEADING = re.compile(r"^(#{2,4})\s+(.*)$", re.MULTILINE)


def _skill_text() -> str:
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def _section(needle: str, *, exact: bool = False) -> str:
    """Return the text of the first heading whose title contains ``needle``.

    The section runs from its own heading to the next heading at the same or a
    shallower level, so an assertion scoped to a section cannot be satisfied by
    prose that lives somewhere else in this long file. Pass ``exact=True`` when a
    substring match would collide with another heading.
    """
    text = _skill_text()
    headings = list(_HEADING.finditer(text))
    for index, match in enumerate(headings):
        title = match.group(2).strip().lower()
        matched = title == needle.lower() if exact else needle.lower() in title
        if not matched:
            continue
        level = len(match.group(1))
        for following in headings[index + 1 :]:
            if len(following.group(1)) <= level:
                return text[match.start() : following.start()]
        return text[match.start() :]
    raise AssertionError(
        f"{SKILL_DIR / 'SKILL.md'}: no heading found containing {needle!r}"
    )


def _heading_offset(pattern: str) -> int:
    """Character offset of the first heading matching ``pattern``."""
    text = _skill_text()
    for match in _HEADING.finditer(text):
        if re.search(pattern, match.group(2).strip(), re.I):
            return match.start()
    raise AssertionError(
        f"{SKILL_DIR / 'SKILL.md'}: no heading matching {pattern!r}"
    )


def _convergence_section() -> str:
    return _section("Main Context Convergence")


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_references_resolve():
    assert_references_resolve(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_tail_block_present():
    assert_tail_block_present(SKILL_DIR)


# --- ri-11 D1: Step 11.6 exists and fires where the design put it ----------


def test_step_11_6_exists_as_a_numbered_step():
    section = _convergence_section()
    assert re.match(r"#{2,4}\s+11\.6\b", section), (
        "The convergence section is not numbered 11.6; D1 places it as a numbered "
        "step between 11.5 and 12, and an unnumbered aside is skippable."
    )


def test_step_11_6_sits_between_step_11_5_and_step_12():
    """D1: after the post-merge cleanup approval gate, before the summary."""
    before = _heading_offset(r"^11\.5\b")
    convergence = _heading_offset(r"^11\.6\b")
    after = _heading_offset(r"^12\b")
    assert before < convergence < after, (
        "Step 11.6 is not ordered between Step 11.5 and Step 12. Ahead of 11.5 it "
        "would converge an un-archived tree; after Step 12 the summary could not "
        "report the convergence it is required to report."
    )


def test_step_11_6_fires_once_per_pass_and_not_once_per_pr():
    """D8: k merges produce one resulting main state, so one convergence."""
    section = _convergence_section()
    assert re.search(r"once per (invocation )?pass", section, re.I), (
        "Step 11.6 does not state that it fires once per invocation pass (D8)."
    )
    assert re.search(r"not once per (pull request|PR)", section, re.I), (
        "Step 11.6 does not rule out the per-PR reading. The per-PR post-merge "
        "pipeline would produce N convergences, N commits, and N index requests."
    )
    assert re.search(r"post-merge pipeline", section, re.I), (
        "Step 11.6 does not say why it is not part of the per-PR post-merge "
        "pipeline, so a future reader may move it there (D1's rejected option)."
    )


def test_step_11_6_does_nothing_when_no_pull_request_merged():
    """D8: k = 0 is a read of main, not a write."""
    section = _convergence_section()
    assert re.search(r"no-merges|nothing (was )?merged|zero .{0,20}merge", section, re.I), (
        "Step 11.6 does not describe the k = 0 case, where a pass that merged "
        "nothing must converge nothing and emit no record."
    )


# --- ri-11 D2: the fixed three-phase sequence ------------------------------


def test_step_11_6_runs_cleanup_before_the_refresh():
    """D2: every merged change is archived before a single refresh reads the tree."""
    section = _convergence_section()
    cleanup = section.find("/cleanup-feature")
    assert cleanup != -1, (
        "Step 11.6 never invokes `/cleanup-feature`; phase 1 has no command."
    )
    driver = section.find("main_convergence.py")
    assert driver != -1, (
        "Step 11.6 never invokes `main_convergence.py`; phases 2 and 3 have no "
        "command."
    )
    assert cleanup < driver, (
        "Step 11.6 orders the refresh before the OpenSpec cleanup. The projection "
        "and decisions producers read the archive, so a refresh that ran first is "
        "stale the instant the archive moves (D2)."
    )


def test_step_11_6_passes_defer_commit_to_cleanup():
    """The other half of cleanup-feature 1.6: cleanup stages, the sync point commits."""
    section = _convergence_section()
    assert "--defer-commit" in section, (
        "Step 11.6 does not pass `--defer-commit` to cleanup, so each archived "
        "change would commit and push itself: N+1 commits for N changes (D3)."
    )
    assert "--post-merge" in section, (
        "Step 11.6 does not pass `--post-merge`, the mode that confirms the PR is "
        "already merged and skips the merge and pre-merge validation stages."
    )
    assert re.search(r"(single|one|exactly one) .{0,40}commit", section, re.I), (
        "Step 11.6 does not state that it produces the single convergence commit "
        "that cleanup deferred to it."
    )


def test_step_11_6_names_the_driver_invocation_and_its_merged_json_input():
    section = _convergence_section()
    assert "--merged-json" in section, (
        "Step 11.6 does not pass `--merged-json`; the driver would then see zero "
        "merges and report `no-merges` for a pass that merged something."
    )
    assert re.search(r"Step 11\b|merged PR records|merged_prs_this_pass", section), (
        "Step 11.6 does not say where the merged-PR records come from (they are "
        "collected during Step 11 and shared with Step 11.5's helper)."
    )


def test_step_11_6_converges_non_openspec_merges_too():
    """D11: a dependency-only pass still converges, through the same operation."""
    section = _convergence_section()
    assert re.search(r"dependabot|non-OpenSpec|dependency-only", section, re.I), (
        "Step 11.6 does not state that a pass with no OpenSpec merge still runs "
        "phases 2 and 3 (D11). Skipping it leaves the drift gate red with no step "
        "in the workflow that would ever fix it."
    )


def test_step_11_6_uses_the_provenance_writing_architecture_target():
    """D10: `make architecture` regenerates artifacts and still leaves drift."""
    section = _convergence_section()
    assert "make architecture-refresh" in section, (
        "Step 11.6 does not name `make architecture-refresh`; provenance is "
        "written only by the staged target, and ri-10's producer routes missing "
        "provenance to drift rather than to `not-configured` (D10)."
    )
    assert not re.search(r"`make architecture`", section), (
        "Step 11.6 still names the bare `make architecture` target, which never "
        "writes provenance."
    )


# --- ri-11 D5: the three guard layers, in order ----------------------------


def test_step_11_6_documents_all_three_guard_layers_in_enforcement_order():
    section = _convergence_section()
    active = section.lower().find("active-agent")
    lock = section.find("sync-point:main-convergence")
    swap = section.lower().find("compare-and-swap")
    assert active != -1, (
        "Step 11.6 does not re-run the active-agent guard. An agent may have set "
        "up a worktree during the merge loop (layer 1)."
    )
    assert lock != -1, (
        "Step 11.6 does not name the coordinator lock key "
        "`sync-point:main-convergence` (layer 2)."
    )
    assert swap != -1, (
        "Step 11.6 does not describe the pre-push compare-and-swap against "
        "`origin/main` (layer 3), the only layer a process that never asked "
        "cannot bypass."
    )
    assert active < lock < swap, (
        "The guard layers are not documented in enforcement order. Layer 2 must "
        "never be reached once layer 1 blocked, or a blocked pass takes a lock it "
        "then has to remember to release."
    )


def test_step_11_6_degrades_when_the_coordinator_is_absent_but_blocks_on_contention():
    section = _convergence_section()
    assert re.search(r"unavailab|absent|degrade", section, re.I), (
        "Step 11.6 does not say that coordinator unavailability degrades to "
        "layers 1 and 3 with a warning. This repo runs solo often enough that a "
        "coordinator-only guard would be missing exactly when it matters."
    )
    assert re.search(r"contention|contended", section, re.I), (
        "Step 11.6 does not distinguish coordinator *contention* (another writer "
        "holds the sync point, which blocks) from *absence* (which warns)."
    )


def test_step_11_6_never_forces_a_losing_push():
    section = _convergence_section()
    assert re.search(r"never force|do not force|not.{0,20}--force", section, re.I), (
        "Step 11.6 does not forbid forcing a losing push."
    )
    assert "--force-with-lease" in section, (
        "Step 11.6 does not rule out `--force-with-lease` by name. A lease that "
        "succeeds still overwrites the other writer's commit; at a sync point, "
        "losing the race is information, not an obstacle (D5)."
    )
    assert re.search(r"resumable", section, re.I), (
        "Step 11.6 does not state that a lost race leaves the operation resumable "
        "with nothing staged discarded."
    )


# --- ri-11 D4: identity and idempotence ------------------------------------


def test_step_11_6_keys_the_operation_on_the_merged_main_sha():
    section = _convergence_section()
    assert re.search(r"merged (main )?(SHA|revision)", section, re.I), (
        "Step 11.6 does not say the operation is keyed on the merged main SHA "
        "(D4). Keying on the set of merged PR numbers is not stable across a "
        "retry, and a per-invocation UUID defeats resume entirely."
    )


def test_step_11_6_documents_both_independent_idempotence_checks():
    section = _convergence_section()
    assert "Context-Refresh-Operation" in section, (
        "Step 11.6 does not name the `Context-Refresh-Operation:` commit trailer, "
        "the half of the idempotence check that survives a fresh clone."
    )
    assert re.search(r"operation record", section, re.I), (
        "Step 11.6 does not name the ri-06 operation record, the half of the "
        "idempotence check that exists before the commit lands."
    )
    assert re.search(r"already[- ]converged", section, re.I), (
        "Step 11.6 does not state what happens when either check finds a prior "
        "convergence: report the existing identity and do nothing."
    )


# --- ri-11 D6: a convergence problem never un-merges anything --------------


def test_step_11_6_can_never_un_merge_or_block_a_merge():
    section = _convergence_section()
    assert re.search(r"never (un-?merge|revert)|cannot (revert|un-?merge)", section, re.I), (
        "Step 11.6 does not state that no convergence outcome reverts a merge. "
        "Merges are terminal by the time this step runs (D6)."
    )
    assert re.search(r"close|re-?open", section, re.I), (
        "Step 11.6 does not rule out closing or re-opening a pull request."
    )
    assert re.search(r"Step 12|summary still|still run", section, re.I), (
        "Step 11.6 does not state that Step 12 and Step 13 run regardless of the "
        "convergence outcome. Suppressing the merge log because a derived "
        "artifact failed loses the more valuable record."
    )


def test_step_11_6_outcome_table_covers_every_refresh_status():
    section = _convergence_section()
    for status in ("succeeded", "degraded", "failed", "not-run"):
        assert status in section, (
            f"Step 11.6's outcome table has no {status!r} row. `degraded` is the "
            "NORMAL outcome whenever the index is deferred, and `not-run` records "
            "a cleanup-only commit -- collapsing either into `failed` would make a "
            "successful partial convergence indistinguishable from a crash."
        )
    assert re.search(r"cleanup-only", section, re.I), (
        "Step 11.6 does not describe the cleanup-only commit that a failed "
        "refresh still produces (D6, D3 failure containment)."
    )


def test_step_11_6_exit_code_never_means_the_merge_failed():
    section = _convergence_section()
    assert re.search(r"exit", section, re.I), (
        "Step 11.6 does not report the driver's exit codes, so an operator cannot "
        "map an exit status onto D6's outcome table."
    )
    assert re.search(r"exit code .{0,60}(never|not) .{0,30}merge", section, re.I), (
        "Step 11.6 does not state that a non-zero exit describes derived context "
        "only and never means a merge failed."
    )


# --- ri-11 D7: the index is enqueued for the final pushed revision ---------


def test_step_11_6_enqueues_one_index_for_the_final_pushed_revision():
    section = _convergence_section()
    assert re.search(r"pushed revision|final pushed|convergence commit", section, re.I), (
        "Step 11.6 does not say which revision is indexed. The convergence commit "
        "changes main's tip, so indexing the merged revision would be stale on "
        "arrival (D7)."
    )
    assert re.search(r"pending", section, re.I), (
        "Step 11.6 does not record the index as `pending`; `semantic_index=None` "
        "would report a clean `succeeded` while making no currency claim."
    )
    assert re.search(r"never await|does not (wait|await)|not awaited", section, re.I), (
        "Step 11.6 does not state that the index is never awaited. Blocking a "
        "sync point on a 30-minute rebuild makes the index a hard dependency of "
        "merging."
    )


# --- ri-11 D9: the tracked record, not the gitignored manifest -------------


def test_step_11_6_lands_the_tracked_convergence_record():
    section = _convergence_section()
    assert "docs/merge-logs/context-convergence.jsonl" in section, (
        "Step 11.6 does not name the tracked convergence record path; the "
        "idempotence check in D4 would have nothing machine-readable to read."
    )
    assert re.search(r"gitignored|untracked", section, re.I), (
        "Step 11.6 does not state that `.git-context/` stays untracked. Tracking "
        "it would reintroduce the repository diff ri-07 D6 exists to prevent."
    )
    assert re.search(r"sha256|digest", section, re.I), (
        "Step 11.6 does not state that the record pins the manifest by digest, "
        "which is what 'the manifest is committed' means in git-native form (D9)."
    )


# --- ri-11: the ownership boundary, including the Step 8 decision ----------


def test_step_11_6_never_archives_or_merges_a_spec_delta():
    section = _convergence_section()
    assert re.search(r"never archives?", section, re.I), (
        "Step 11.6 does not state that it never archives. Duplicating archive "
        "logic in two skills makes the first divergence silent spec corruption."
    )
    assert re.search(r"spec delta|spec-delta", section, re.I), (
        "Step 11.6 does not state that the spec-delta merge stays with "
        "cleanup-feature."
    )
    assert re.search(r"migrat", section, re.I), (
        "Step 11.6 does not state that task migration stays with cleanup-feature."
    )


def test_step_11_6_decides_who_owns_local_branch_deletion_and_lock_release():
    """The gap D3 left open: cleanup-feature 1.6 skips Steps 8.5 and 9, not 8.

    Two skills each assuming the other deletes the feature branch is how
    orphaned branches and held locks happen, so the boundary is stated here
    rather than inferred.
    """
    section = _convergence_section()
    assert re.search(r"Step 8(?!\.\d)", section), (
        "Step 11.6 does not decide who owns cleanup-feature's Step 8 (local "
        "branch deletion and lock release). cleanup-feature 1.6 names only Steps "
        "8.5 and 9 as skipped, so Step 8's owner is undecided until this says so."
    )
    assert re.search(r"branch deletion|delete .{0,30}branch|git branch -d", section, re.I), (
        "Step 11.6's Step 8 decision does not mention local branch deletion."
    )
    assert re.search(r"lock release|release .{0,30}lock", section, re.I), (
        "Step 11.6's Step 8 decision does not mention lock release, which is the "
        "half of Step 8 the sync point mechanically cannot perform."
    )
    assert re.search(r"owner-scoped|owns the lock|which agent|agent/session", section, re.I), (
        "Step 11.6 states the Step 8 decision without its reason. Lock release is "
        "owner-scoped: only the cleanup invocation knows which agent/session holds "
        "the locks for the feature branch's files."
    )
    assert re.search(r"8\.5|worktree removal", section, re.I), (
        "Step 11.6 does not contrast Step 8 with the steps cleanup actually does "
        "skip (8.5 and 9), which is what makes the decision legible."
    )
