"""Workspace guard for vendor review dispatch.

Vendor CLIs run against the shared checkout with full ambient authority. The
HEAD guard (issue #349) catches a moved HEAD; this guard catches the other side
effect seen in practice: files written into the working tree. On 2026-09-14 a
reviewer left ``pr484_review.json`` at the repository root, where the next
``main_convergence.py`` run (which stages with ``git add -A``) would have
committed it to main.

New untracked files are moved out of the tree into a quarantine directory, not
deleted: that stray file turned out to be the only readable copy of one
vendor's findings.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _helpers import capture_untracked, quarantine_new_untracked  # noqa: E402


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
    (repo / ".gitignore").write_text("__pycache__/\n")
    (repo / "tracked.txt").write_text("one\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "c1")
    monkeypatch.chdir(repo)
    return repo


def test_new_untracked_file_is_moved_to_quarantine(repo: Path, tmp_path: Path) -> None:
    before = capture_untracked()
    (repo / "pr484_review.json").write_text('{"findings": []}\n')
    (repo / "nested").mkdir()
    (repo / "nested" / "notes.md").write_text("vendor scratch\n")

    dest = tmp_path / "quarantine"
    guard = quarantine_new_untracked(before, dest)

    assert guard["new_untracked"] == ["nested/notes.md", "pr484_review.json"]
    assert guard["quarantined_to"] == str(dest)
    assert guard["errors"] == []
    assert not (repo / "pr484_review.json").exists()
    assert (dest / "pr484_review.json").read_text() == '{"findings": []}\n'
    assert (dest / "nested" / "notes.md").exists()
    assert _git(repo, "status", "--porcelain") == ""


def test_untracked_file_that_existed_before_dispatch_stays(
    repo: Path, tmp_path: Path,
) -> None:
    (repo / "operator_wip.py").write_text("# not the vendor's\n")
    before = capture_untracked()

    guard = quarantine_new_untracked(before, tmp_path / "quarantine")

    assert guard["new_untracked"] == []
    assert guard["quarantined_to"] is None
    assert (repo / "operator_wip.py").exists()
    assert not (tmp_path / "quarantine").exists()


def test_ignored_files_are_not_touched(repo: Path, tmp_path: Path) -> None:
    before = capture_untracked()
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "x.pyc").write_bytes(b"\0")

    guard = quarantine_new_untracked(before, tmp_path / "quarantine")

    assert guard["new_untracked"] == []
    assert (repo / "__pycache__" / "x.pyc").exists()


def test_capture_from_a_subdirectory_uses_repo_relative_paths(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")
    before = capture_untracked()
    (repo / "stray.txt").write_text("x\n")

    guard = quarantine_new_untracked(before, tmp_path / "quarantine")

    assert guard["new_untracked"] == ["stray.txt"]
    assert not (repo / "stray.txt").exists()


def test_dispatch_quarantines_files_a_vendor_writes(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wiring: dispatch_vendor_reviews runs the guard and reports it."""
    import vendor_review

    class FakeOrchestrator:
        adapters = {"fake": object()}

        @classmethod
        def from_coordinator(cls) -> "FakeOrchestrator":
            return cls()

        def discover_reviewers(self, exclude_vendor: str):
            return [SimpleNamespace(available=True)]

        def dispatch_and_wait(self, *, cwd: Path, **_kwargs):
            (Path(cwd) / "pr99_review.json").write_text("{}\n")
            return []

    fake = ModuleType("review_dispatcher")
    fake.ReviewOrchestrator = FakeOrchestrator
    fake.ReviewResult = object
    monkeypatch.setitem(sys.modules, "review_dispatcher", fake)
    monkeypatch.setattr(vendor_review, "build_review_prompt", lambda *_a: "prompt")
    monkeypatch.setenv("MERGE_VENDOR_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    result = vendor_review.dispatch_vendor_reviews(99, {"changed_lines": 100})

    guard = result["workspace_guard"]
    assert guard["new_untracked"] == ["pr99_review.json"]
    assert not (repo / "pr99_review.json").exists()
    assert list((tmp_path / "artifacts").rglob("pr99_review.json"))
