"""Tests for plan vs implementation vs automation classification."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from classify_kind import classify_ci_failure, classify_kind  # noqa: E402
from build_plan import build_plan  # noqa: E402
from merge_plan import validate_plan  # noqa: E402


def test_planning_artifact_only_openspec_pr_is_plan() -> None:
    result = classify_kind(
        {
            "origin": "openspec",
            "branch": "openspec/add-widget",
            "change_id": "add-widget",
        },
        ["openspec/changes/add-widget/proposal.md", "openspec/changes/add-widget/tasks.md"],
    )
    assert result["kind"] == "plan"
    assert result["change_id"] == "add-widget"
    assert result["remediation_skill"] == "iterate-on-plan"
    assert result["kind_overridden"] is False


def test_openspec_pr_touching_product_code_is_implementation() -> None:
    result = classify_kind(
        {"origin": "openspec", "branch": "openspec/add-widget"},
        ["openspec/changes/add-widget/proposal.md", "skills/foo/SKILL.md"],
    )
    assert result["kind"] == "implementation"
    assert result["remediation_skill"] == "iterate-on-implementation"


def test_dependabot_origin_is_automation() -> None:
    result = classify_kind(
        {"origin": "dependabot", "branch": "dependabot/pip/x"},
        ["requirements.txt"],
    )
    assert result["kind"] == "automation"
    assert result["remediation_skill"] == "none"


def test_operator_override_wins_over_heuristic() -> None:
    result = classify_kind(
        {"origin": "openspec", "branch": "openspec/add-widget"},
        ["skills/foo/SKILL.md"],
        kind_override="plan",
    )
    assert result["kind"] == "plan"
    assert result["remediation_skill"] == "iterate-on-plan"
    assert result["kind_overridden"] is True


def test_build_plan_persists_override_not_reheuristic() -> None:
    prs = [
        {
            "number": 7,
            "title": "Plan PR",
            "branch": "openspec/add-widget",
            "origin": "openspec",
            "ci_state": "clean",
            "kind_override": "plan",
            "changed_files": ["skills/foo/SKILL.md"],
        }
    ]
    staleness = {7: {"staleness": "fresh", "pr_files": ["skills/foo/SKILL.md"]}}
    comments = {7: {"unresolved_count": 0}}
    plan = build_plan(prs, staleness, comments, generated_at="2026-09-10T00:00:00+00:00")
    validate_plan(plan)
    node = plan["nodes"][0]
    assert node["definition"]["kind"] == "plan"
    assert node["definition"]["kind_overridden"] is True
    assert node["definition"]["remediation_skill"] == "iterate-on-plan"


def test_stale_base_class_from_ci_merge_base_stale() -> None:
    assert (
        classify_ci_failure(
            {},
            {"ci_merge_base_stale": True},
            "blocked",
        )
        == "stale_base"
    )


def test_clean_ci_has_no_failure_class() -> None:
    assert classify_ci_failure({}, {}, "clean") is None


# --------------------------------------------------------------------------- #
# claude/* branches: the diff is the authority the branch name only approximates
# --------------------------------------------------------------------------- #


def _claude_pr(**overrides: object) -> dict:
    pr: dict = {"origin": "openspec", "branch": "claude/add-widget-xy12ab"}
    pr.update(overrides)
    return pr


def test_claude_branch_planning_diff_is_a_plan() -> None:
    """Claude Code cloud sessions push to claude/*, not openspec/*.

    `github_classifier.classify_pr` leaves their `change_id` unset unless the
    body carries an `Implements OpenSpec:` marker, which is optional and often
    absent. The branch rule only matched `openspec/`, so such a PR had no change
    id, could not be recognized as a plan, and was routed to `quick-task`
    instead of `iterate-on-plan` -- a wrong-skill pairing the merge conductor
    treats as a halt condition.
    """
    result = classify_kind(
        _claude_pr(),
        [
            "openspec/changes/add-widget/proposal.md",
            "openspec/changes/add-widget/tasks.md",
        ],
    )

    assert result["kind"] == "plan"
    assert result["change_id"] == "add-widget"
    assert result["remediation_skill"] == "iterate-on-plan"


def test_claude_branch_mixed_diff_routes_to_iterate_on_implementation() -> None:
    """A change id is worth recovering even when the kind stays implementation."""
    result = classify_kind(
        _claude_pr(),
        [
            "openspec/changes/add-widget/proposal.md",
            "skills/widget/scripts/widget.py",
        ],
    )

    assert result["kind"] == "implementation"
    assert result["change_id"] == "add-widget"
    assert result["remediation_skill"] == "iterate-on-implementation"


def test_explicit_change_id_still_wins_over_the_diff() -> None:
    result = classify_kind(
        _claude_pr(change_id="from-body-marker"),
        ["openspec/changes/add-widget/proposal.md"],
    )

    assert result["change_id"] == "from-body-marker"


def test_openspec_branch_name_still_wins_over_the_diff() -> None:
    result = classify_kind(
        {"origin": "openspec", "branch": "openspec/from-branch"},
        ["openspec/changes/add-widget/proposal.md"],
    )

    assert result["change_id"] == "from-branch"


def test_archived_change_paths_do_not_yield_the_literal_archive() -> None:
    result = classify_kind(
        _claude_pr(),
        ["openspec/changes/archive/2026-01-01-add-widget/proposal.md"],
    )

    assert result["change_id"] is None


def test_a_diff_spanning_two_change_directories_is_not_a_change_id() -> None:
    """Ambiguity is not a change id; guessing one would route remediation wrong."""
    result = classify_kind(
        _claude_pr(),
        [
            "openspec/changes/add-widget/proposal.md",
            "openspec/changes/add-gadget/proposal.md",
        ],
    )

    assert result["change_id"] is None
    assert result["kind"] == "implementation"


def test_a_diff_touching_no_change_directory_keeps_quick_task() -> None:
    result = classify_kind(_claude_pr(), ["skills/widget/scripts/widget.py"])

    assert result["change_id"] is None
    assert result["remediation_skill"] == "quick-task"


def test_automation_origin_still_wins_over_a_planning_diff() -> None:
    result = classify_kind(
        {"origin": "dependabot", "branch": "dependabot/pip/x"},
        ["openspec/changes/add-widget/proposal.md"],
    )

    assert result["kind"] == "automation"
