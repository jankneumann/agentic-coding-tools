"""An already-current PR branch is not a failed refresh.

GitHub's Update Branch API answers a PR whose branch already contains its base
with a 422, ``There are no new commits on the base branch.`` Both update-branch
callers matched only older wording, so they reported that 422 as a failure.

In ``execute_plan`` this was a deadlock: a failed refresh keeps
``needs_revalidation`` set, and every retry refreshes again, so a node flagged by
an upstream merge could never merge once its first refresh had landed. Observed
live on 2026-09-14 on PRs #520 and #524. The stderr below is that live text.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _helpers import update_branch_already_current  # noqa: E402
from auto_rebase import _refresh_pr_branch  # noqa: E402
from merge_pr import refresh_branch  # noqa: E402

LIVE_422 = "gh: There are no new commits on the base branch. (HTTP 422)"
PR_VIEW = json.dumps({"headRefOid": "abc123def456", "baseRefName": "main"})


def _failed(stderr: str) -> SimpleNamespace:
    return SimpleNamespace(returncode=1, stdout="", stderr=stderr)


@pytest.mark.parametrize(
    "stderr",
    [
        LIVE_422,
        "gh: THERE ARE NO NEW COMMITS ON THE BASE BRANCH. (HTTP 422)",
        "Branch is already up-to-date",
        "merge-upstream is not behind the upstream",
    ],
)
def test_current_branch_markers(stderr: str) -> None:
    assert update_branch_already_current(stderr) is True


@pytest.mark.parametrize(
    "stderr",
    [
        "gh: merge conflict between base and head (HTTP 422)",
        "gh: expected head sha didn't match current head ref. (HTTP 422)",
        "",
    ],
)
def test_real_failures_are_not_current(stderr: str) -> None:
    assert update_branch_already_current(stderr) is False


@patch("merge_pr.run_gh_unchecked", return_value=_failed(LIVE_422))
@patch("merge_pr.run_gh", return_value=PR_VIEW)
def test_refresh_branch_treats_live_422_as_up_to_date(_view, _update) -> None:
    result = refresh_branch(42)

    assert result["success"] is True
    assert result["was_stale"] is False
    assert "up to date" in result["message"]


@patch("merge_pr.run_gh_unchecked", return_value=_failed("gh: merge conflict between base and head (HTTP 422)"))
@patch("merge_pr.run_gh", return_value=PR_VIEW)
def test_refresh_branch_still_fails_on_conflict(_view, _update) -> None:
    result = refresh_branch(42)

    assert result["success"] is False
    assert "merge conflict" in result["reason"]


@patch("auto_rebase.run_gh_unchecked", return_value=_failed(LIVE_422))
@patch("auto_rebase.run_gh", return_value=PR_VIEW)
def test_cascade_refresh_treats_live_422_as_already_fresh(_view, _update) -> None:
    result = _refresh_pr_branch(42)

    assert result == {"success": True, "pr_number": 42, "already_fresh": True}
