"""Change-id recovery for branches the `openspec/` prefix rule cannot name.

Lives in the canonical skill test tree (`skills/tests/<skill-name>/`) per
AGENTS.md, so the documented `pytest skills/tests/` invocation covers it. The
older `scripts/tests/test_classify_kind.py` keeps the pre-existing kind cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SUITE_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _SUITE_DIR.parents[1]
for _extra in (
    _SKILLS_DIR / "merge-pull-requests" / "scripts",
    _SKILLS_DIR / "shared",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from classify_kind import classify_kind  # noqa: E402


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
