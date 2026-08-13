"""HEAD-mutation guard for vendor review dispatch (issue #349).

Vendor CLIs dispatched against the shared checkout have been observed
checking out FETCH_HEAD, silently detaching HEAD. These tests pin the
capture/verify/restore helpers and the merge-time detached-HEAD refusal.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _helpers import capture_head, verify_and_restore_head  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo),
         "-c", "user.name=test", "-c", "user.email=test@test",
         *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "f.txt").write_text("one\n")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", "c1")
    (repo / "f.txt").write_text("two\n")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", "c2")
    monkeypatch.chdir(repo)
    return repo


class TestCaptureHead:
    def test_on_branch(self, repo: Path) -> None:
        head = capture_head()
        assert head["branch"] == "main"
        assert len(head["sha"]) == 40

    def test_detached(self, repo: Path) -> None:
        first = _git(repo, "rev-parse", "HEAD~1")
        _git(repo, "checkout", first)
        head = capture_head()
        assert head["branch"] is None
        assert head["sha"] == first


class TestVerifyAndRestore:
    def test_no_drift(self, repo: Path) -> None:
        before = capture_head()
        result = verify_and_restore_head(before)
        assert result["drift_detected"] is False
        assert result["restored"] is False
        assert result["error"] is None

    def test_vendor_detach_is_detected_and_restored(self, repo: Path) -> None:
        """The realized #349 shape: a checkout to a bare SHA mid-dispatch."""
        before = capture_head()
        _git(repo, "checkout", _git(repo, "rev-parse", "HEAD~1"))

        result = verify_and_restore_head(before)

        assert result["drift_detected"] is True
        assert result["restored"] is True
        assert result["after"]["branch"] is None
        now = capture_head()
        assert now["branch"] == "main"
        assert now["sha"] == before["sha"]

    def test_originally_detached_reports_unrestorable(self, repo: Path) -> None:
        first = _git(repo, "rev-parse", "HEAD~1")
        _git(repo, "checkout", first)
        before = capture_head()
        _git(repo, "checkout", "main")

        result = verify_and_restore_head(before)

        assert result["drift_detected"] is True
        assert result["restored"] is False
        assert "no branch to restore" in result["error"]


class TestMergeDetachedHeadGuard:
    def test_merge_refuses_on_detached_head(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import merge_pr as merge_pr_mod

        _git(repo, "checkout", _git(repo, "rev-parse", "HEAD~1"))

        def _explode(*args: object, **kwargs: object) -> dict:
            raise AssertionError("validate_pr must not run on a detached HEAD")

        monkeypatch.setattr(merge_pr_mod, "validate_pr", _explode)
        result = merge_pr_mod.merge_pr(123)

        assert result["success"] is False
        assert result["reason"] == "detached_head"

    def test_merge_proceeds_past_guard_on_branch(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import merge_pr as merge_pr_mod

        sentinel = {"can_merge": False, "is_draft": True, "approved": True,
                    "mergeable": "MERGEABLE", "checks_failed": False,
                    "checks_pending": False, "review_decision": "APPROVED"}
        monkeypatch.setattr(merge_pr_mod, "validate_pr", lambda n: dict(sentinel))
        result = merge_pr_mod.merge_pr(123, dry_run=True)

        assert result.get("reason") != "detached_head"
        assert result["dry_run"] is True
