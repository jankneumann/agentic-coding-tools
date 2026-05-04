"""Tests for --force-approval and the remote-branch deletion fallback.

Covers:
- merge_pr() refuses an unapproved PR by default with a hint to --force-approval
- merge_pr(force_approval=True) flips approved/can_merge and reaches _try_merge
- _try_merge falls back to a REST DELETE when gh pr merge succeeds at merging
  but its --delete-branch step aborts before the remote DELETE
- The fallback is skipped for fork PRs (no remote-branch access)
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Add scripts dir to path so we can import merge_pr
sys.path.insert(0, str(Path(__file__).parent.parent))

import merge_pr as mp


def _validation_response(
    *, approved: bool = False, mergeable: str = "MERGEABLE",
    is_draft: bool = False, branch: str = "openspec/test-feature",
) -> dict[str, Any]:
    """Construct a validate_pr-shaped dict for monkey-patching."""
    return {
        "pr_number": 42,
        "title": "Test PR",
        "branch": branch,
        "is_draft": is_draft,
        "is_fork": False,
        "mergeable": mergeable,
        "has_conflicts": mergeable == "CONFLICTING",
        "check_summary": "passing",
        "checks_passing": True,
        "checks_pending": False,
        "checks_failed": False,
        "check_details": [],
        "review_decision": "APPROVED" if approved else "REVIEW_REQUIRED",
        "approved": approved,
        "approval_may_be_stale": False,
        "pending_reviewers": [],
        "can_merge": (
            mergeable == "MERGEABLE" and approved
            and not is_draft
        ),
    }


class TestForceApprovalGate:
    """The approval gate distinguishes default and --force-approval paths."""

    def test_default_blocks_unapproved_with_hint_to_force_flag(self) -> None:
        validation = _validation_response(approved=False)
        with patch.object(mp, "validate_pr", return_value=validation):
            result = mp.merge_pr(42, "rebase", dry_run=False)
        assert result["success"] is False
        assert "approval required" in result["reason"].lower()
        assert "--force-approval" in result["reason"]
        assert "bypassed_approval" not in result

    def test_force_approval_flips_validation_view_in_dry_run(self) -> None:
        validation = _validation_response(approved=False)
        with patch.object(mp, "validate_pr", return_value=validation):
            result = mp.merge_pr(42, "rebase", dry_run=True, force_approval=True)
        assert result["dry_run"] is True
        assert result["would_merge"] is True
        assert result["bypassed_approval"] is True
        # Validation view records BOTH the override flag and the original
        # decision so the audit trail survives downstream consumers.
        assert result["validation"]["bypassed_approval"] is True
        assert result["validation"]["original_review_decision"] == "REVIEW_REQUIRED"
        assert result["validation"]["approved"] is True
        assert result["validation"]["can_merge"] is True

    def test_force_approval_does_not_override_conflicts(self) -> None:
        validation = _validation_response(
            approved=False, mergeable="CONFLICTING",
        )
        with patch.object(mp, "validate_pr", return_value=validation):
            result = mp.merge_pr(42, "rebase", dry_run=False, force_approval=True)
        assert result["success"] is False
        assert "conflict" in result["reason"].lower()

    def test_force_approval_reaches_try_merge_and_records_bypass(self) -> None:
        validation = _validation_response(approved=False)
        merge_result = {
            "action": "merge", "success": True, "status": "merged",
            "pr_number": 42, "strategy": "rebase",
        }
        with patch.object(mp, "validate_pr", return_value=validation), \
                patch.object(mp, "_try_merge", return_value=merge_result) as try_merge:
            result = mp.merge_pr(42, "rebase", dry_run=False, force_approval=True)
        assert result["success"] is True
        assert result["bypassed_approval"] is True
        # Branch must be threaded through so the post-merge fallback can use it
        try_merge.assert_called_once()
        kwargs = try_merge.call_args.kwargs
        assert kwargs.get("branch") == "openspec/test-feature"


class TestRemoteBranchDeleteFallback:
    """When `gh pr merge --delete-branch` aborts after a successful merge,
    fall back to the REST DELETE for the remote ref."""

    def _completed(self, *, returncode: int, stderr: str = "") -> Any:
        result = MagicMock()
        result.returncode = returncode
        result.stderr = stderr
        return result

    def test_fallback_runs_when_merge_state_is_merged_but_gh_failed(self) -> None:
        # Force the merge-queue path off so we go through the direct path
        with patch.object(mp, "_has_merge_queue", return_value=False), \
                patch.object(
                    mp, "run_gh_unchecked",
                    side_effect=[
                        # gh pr merge: returns non-zero (local branch update fatal)
                        self._completed(
                            returncode=1,
                            stderr=(
                                "fatal: not a git repository (or any of the "
                                "parent directories): .git"
                            ),
                        ),
                        # gh api DELETE refs/heads/<branch>: 204 No Content
                        self._completed(returncode=0),
                    ],
                ), \
                patch.object(
                    mp, "get_pr_status",
                    return_value={"state": "MERGED"},
                ):
            resp = mp._try_merge(
                42, "rebase", is_fork=False,
                branch="openspec/test-feature",
            )
        assert resp["success"] is True
        assert resp["status"] == "merged"
        assert resp["remote_branch_delete"]["deleted"] is True
        assert resp["remote_branch_delete"]["branch"] == "openspec/test-feature"
        assert "API fallback" in resp["warning"]

    def test_fallback_skipped_for_fork_pr(self) -> None:
        with patch.object(mp, "_has_merge_queue", return_value=False), \
                patch.object(
                    mp, "run_gh_unchecked",
                    return_value=self._completed(returncode=1, stderr="boom"),
                ), \
                patch.object(
                    mp, "get_pr_status",
                    return_value={"state": "MERGED"},
                ):
            resp = mp._try_merge(
                42, "squash", is_fork=True,
                branch="openspec/test-feature",
            )
        assert resp["success"] is True
        assert "remote_branch_delete" not in resp
        assert "Fork PR" in resp.get("note", "")

    def test_fallback_skipped_when_no_branch_threaded(self) -> None:
        # Older callers may not pass a branch. Don't 500 — just skip.
        with patch.object(mp, "_has_merge_queue", return_value=False), \
                patch.object(
                    mp, "run_gh_unchecked",
                    return_value=self._completed(returncode=1, stderr="boom"),
                ), \
                patch.object(
                    mp, "get_pr_status",
                    return_value={"state": "MERGED"},
                ):
            resp = mp._try_merge(42, "rebase", is_fork=False, branch="")
        assert resp["success"] is True
        assert "remote_branch_delete" not in resp

    def test_already_absent_remote_ref_is_treated_as_deleted(self) -> None:
        with patch.object(
                mp, "run_gh_unchecked",
                return_value=self._completed(
                    returncode=1, stderr="Reference does not exist",
                ),
        ):
            result = mp._delete_remote_branch_via_api("openspec/gone")
        assert result["deleted"] is True
        assert result["already_absent"] is True
