"""Tests for the conditional approval gate in merge_pr.py.

Covers:
- ``_base_branch_requires_approval`` returns False for unprotected branches (404)
- Returns False when protection exists but no review requirement
- Returns True when ``required_approving_review_count >= 1``
- Fail-closed on ambiguous failures (403, timeout, parse error, empty base)
- ``merge_pr`` skips the approval gate when ``approval_required`` is False
- ``merge_pr`` still gates when approval is required and not allowed
- ``--allow-unapproved`` bypasses the gate even when approval is required
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

# Add the skill's scripts dir to path so we can import merge_pr.
SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "merge-pull-requests" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import merge_pr  # noqa: E402


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    """Minimal stand-in for subprocess.CompletedProcess used by run_gh_unchecked."""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestBaseBranchRequiresApproval:
    """Mirror GitHub's enforcement: only gate when protection actually requires it."""

    def test_404_unprotected_branch_returns_false(self, monkeypatch) -> None:
        # Solo-dev common case: gh api returns 404 because no protection rule exists.
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *_a, **_k: _completed(
                1, stderr="gh: Branch not protected (HTTP 404)\n",
            ),
        )
        assert merge_pr._base_branch_requires_approval("main") is False

    def test_protection_without_review_requirement_returns_false(
        self, monkeypatch,
    ) -> None:
        # Protection exists (e.g. status-check requirement) but no review requirement.
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *_a, **_k: _completed(0, stdout='{"required_status_checks": {}}'),
        )
        assert merge_pr._base_branch_requires_approval("main") is False

    def test_zero_required_approvals_returns_false(self, monkeypatch) -> None:
        body = (
            '{"required_pull_request_reviews": '
            '{"required_approving_review_count": 0}}'
        )
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *_a, **_k: _completed(0, stdout=body),
        )
        assert merge_pr._base_branch_requires_approval("main") is False

    def test_one_required_approval_returns_true(self, monkeypatch) -> None:
        body = (
            '{"required_pull_request_reviews": '
            '{"required_approving_review_count": 1}}'
        )
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *_a, **_k: _completed(0, stdout=body),
        )
        assert merge_pr._base_branch_requires_approval("main") is True

    def test_two_required_approvals_returns_true(self, monkeypatch) -> None:
        body = (
            '{"required_pull_request_reviews": '
            '{"required_approving_review_count": 2}}'
        )
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *_a, **_k: _completed(0, stdout=body),
        )
        assert merge_pr._base_branch_requires_approval("main") is True

    def test_empty_base_branch_fails_closed(self, monkeypatch) -> None:
        # No base branch known → can't probe → assume protected.
        called = []
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *a, **k: called.append((a, k)) or _completed(0, stdout="{}"),
        )
        assert merge_pr._base_branch_requires_approval("") is True
        assert called == [], "should not call gh when base branch is empty"

    def test_403_fails_closed(self, monkeypatch) -> None:
        # No permission to read protection → preserve strict behavior.
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *_a, **_k: _completed(
                1, stderr="gh: Resource not accessible (HTTP 403)\n",
            ),
        )
        assert merge_pr._base_branch_requires_approval("main") is True

    def test_timeout_fails_closed(self, monkeypatch) -> None:
        def _raise(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

        monkeypatch.setattr(merge_pr, "run_gh_unchecked", _raise)
        assert merge_pr._base_branch_requires_approval("main") is True

    def test_unparseable_response_fails_closed(self, monkeypatch) -> None:
        monkeypatch.setattr(
            merge_pr, "run_gh_unchecked",
            lambda *_a, **_k: _completed(0, stdout="not json"),
        )
        assert merge_pr._base_branch_requires_approval("main") is True


class TestMergePrApprovalGate:
    """End-to-end check of the gate behavior inside merge_pr()."""

    def _validation(self, *, approved: bool, approval_required: bool) -> dict:
        return {
            "pr_number": 1,
            "title": "test",
            "branch": "feature",
            "base_branch": "main",
            "is_draft": False,
            "is_fork": False,
            "mergeable": "MERGEABLE",
            "has_conflicts": False,
            "check_summary": "passing",
            "checks_passing": True,
            "checks_pending": False,
            "checks_failed": False,
            "check_details": [],
            "review_decision": "APPROVED" if approved else "REVIEW_REQUIRED",
            "approved": approved,
            "approval_required": approval_required,
            "approval_may_be_stale": False,
            "pending_reviewers": [],
            "can_merge": approved or not approval_required,
        }

    def test_unapproved_pr_blocks_when_approval_required(self, monkeypatch) -> None:
        monkeypatch.setattr(
            merge_pr, "validate_pr",
            lambda _n: self._validation(approved=False, approval_required=True),
        )
        called = []
        monkeypatch.setattr(
            merge_pr, "_try_merge",
            lambda *a, **k: called.append((a, k)) or {"success": True},
        )

        result = merge_pr.merge_pr(1)

        assert result["success"] is False
        assert "approval required" in result["reason"].lower()
        assert called == [], "merge must not be attempted when gate blocks"

    def test_unapproved_pr_merges_when_approval_not_required(
        self, monkeypatch,
    ) -> None:
        # Solo-dev path: no protection → gate skipped.
        monkeypatch.setattr(
            merge_pr, "validate_pr",
            lambda _n: self._validation(approved=False, approval_required=False),
        )
        called = []

        def fake_merge(pr, strategy, is_fork):
            called.append((pr, strategy, is_fork))
            return {
                "action": "merge", "success": True,
                "status": "merged", "pr_number": pr, "strategy": strategy,
            }

        monkeypatch.setattr(merge_pr, "_try_merge", fake_merge)

        result = merge_pr.merge_pr(1, strategy="squash")

        assert result["success"] is True
        assert called == [(1, "squash", False)]

    def test_allow_unapproved_bypasses_gate_when_required(self, monkeypatch) -> None:
        # Admin override: protection requires approval but operator forces through.
        monkeypatch.setattr(
            merge_pr, "validate_pr",
            lambda _n: self._validation(approved=False, approval_required=True),
        )
        called = []

        def fake_merge(pr, strategy, is_fork):
            called.append((pr, strategy, is_fork))
            return {
                "action": "merge", "success": True,
                "status": "merged", "pr_number": pr, "strategy": strategy,
            }

        monkeypatch.setattr(merge_pr, "_try_merge", fake_merge)

        result = merge_pr.merge_pr(1, strategy="squash", allow_unapproved=True)

        assert result["success"] is True
        assert called == [(1, "squash", False)]

    def test_approved_pr_merges_regardless_of_requirement(self, monkeypatch) -> None:
        monkeypatch.setattr(
            merge_pr, "validate_pr",
            lambda _n: self._validation(approved=True, approval_required=True),
        )
        monkeypatch.setattr(
            merge_pr, "_try_merge",
            lambda *_a, **_k: {"action": "merge", "success": True},
        )
        result = merge_pr.merge_pr(1)
        assert result["success"] is True


class TestCanMergeFieldRespectsApprovalRequired:
    """``validation['can_merge']`` reflects the new conditional logic."""

    def test_can_merge_true_when_unapproved_but_not_required(
        self, monkeypatch,
    ) -> None:
        # Stub get_pr_status to return a fully clean PR with no approval.
        monkeypatch.setattr(
            merge_pr, "get_pr_status",
            lambda _n: {
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS"}],
                "reviewDecision": "REVIEW_REQUIRED",
                "headRefName": "feature",
                "baseRefName": "main",
                "title": "t",
                "isDraft": False,
                "isCrossRepository": False,
                "reviewRequests": [],
            },
        )
        # Branch is unprotected.
        monkeypatch.setattr(
            merge_pr, "_base_branch_requires_approval", lambda _b: False,
        )

        result = merge_pr.validate_pr(1)
        assert result["approval_required"] is False
        assert result["approved"] is False
        assert result["can_merge"] is True

    def test_can_merge_false_when_unapproved_and_required(
        self, monkeypatch,
    ) -> None:
        monkeypatch.setattr(
            merge_pr, "get_pr_status",
            lambda _n: {
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "statusCheckRollup": [{"name": "ci", "conclusion": "SUCCESS"}],
                "reviewDecision": "REVIEW_REQUIRED",
                "headRefName": "feature",
                "baseRefName": "main",
                "title": "t",
                "isDraft": False,
                "isCrossRepository": False,
                "reviewRequests": [],
            },
        )
        monkeypatch.setattr(
            merge_pr, "_base_branch_requires_approval", lambda _b: True,
        )

        result = merge_pr.validate_pr(1)
        assert result["approval_required"] is True
        assert result["approved"] is False
        assert result["can_merge"] is False
