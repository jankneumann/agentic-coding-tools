from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "validate-feature" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validation_worktree import (  # noqa: E402
    DirtyValidationSourceError,
    validation_worktree,
)


def _git(repo: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "tests@example.com")
    _git(root, "config", "user.name", "Tests")
    (root / "tracked.txt").write_text("committed\n")
    (root / "other.txt").write_text("other committed\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    return root


def test_clean_ephemeral_run_uses_head_and_removes_scratch(repo: Path) -> None:
    expected_head = _git(repo, "rev-parse", "HEAD")

    with validation_worktree(repo, "example") as run:
        scratch = run.path
        assert run.ephemeral is True
        assert scratch != repo
        assert scratch.exists()
        assert run.validated_commit == expected_head
        assert _git(scratch, "rev-parse", "HEAD") == expected_head

    assert not scratch.exists()
    assert str(scratch) not in _git(repo, "worktree", "list", "--porcelain")


def test_dirty_worktree_fails_fast_with_include_dirty_guidance(repo: Path) -> None:
    (repo / "tracked.txt").write_text("dirty\n")

    with pytest.raises(DirtyValidationSourceError, match="--include-dirty"):
        with validation_worktree(repo, "example"):
            pass


def test_include_dirty_materializes_index_worktree_and_untracked_state(repo: Path) -> None:
    (repo / "tracked.txt").write_text("staged\n")
    _git(repo, "add", "tracked.txt")
    (repo / "other.txt").write_text("unstaged\n")
    (repo / "untracked.txt").write_text("untracked\n")

    with validation_worktree(repo, "example", include_dirty=True) as run:
        assert (run.path / "tracked.txt").read_text() == "staged\n"
        assert (run.path / "other.txt").read_text() == "unstaged\n"
        assert (run.path / "untracked.txt").read_text() == "untracked\n"
        assert run.validated_tree != _git(repo, "rev-parse", "HEAD^{tree}")

    assert (repo / "tracked.txt").read_text() == "staged\n"
    assert (repo / "other.txt").read_text() == "unstaged\n"
    assert (repo / "untracked.txt").read_text() == "untracked\n"


def test_results_are_copied_back_before_teardown_and_no_residue_escapes(repo: Path) -> None:
    change_dir = repo / "openspec" / "changes" / "example"
    change_dir.mkdir(parents=True)
    (change_dir / ".gitkeep").write_text("")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add change")

    with validation_worktree(repo, "example") as run:
        scratch_change = run.path / "openspec" / "changes" / "example"
        (scratch_change / "validation-report.md").write_text("report\n")
        (scratch_change / "validation-findings.json").write_text("{}\n")
        (run.path / "deploy-residue.log").write_text("discard me\n")
        scratch = run.path

    findings = json.loads((change_dir / "validation-findings.json").read_text())
    assert findings["validated_commit"] == run.validated_commit
    assert findings["validated_tree"] == run.validated_tree
    report = (change_dir / "validation-report.md").read_text()
    assert f"**Validated commit**: {run.validated_commit}" in report
    assert f"**Validated tree**: {run.validated_tree}" in report
    assert not (repo / "deploy-residue.log").exists()
    assert not scratch.exists()


def test_scratch_is_removed_when_validation_raises(repo: Path) -> None:
    with pytest.raises(RuntimeError, match="validation failed"):
        with validation_worktree(repo, "example") as run:
            scratch = run.path
            raise RuntimeError("validation failed")

    assert not scratch.exists()


def test_cloud_harness_downgrades_to_in_place(repo: Path, caplog: pytest.LogCaptureFixture) -> None:
    class CloudProfile:
        isolation_provided = True
        source = "test-cloud"

    with validation_worktree(repo, "example", detector=lambda: CloudProfile()) as run:
        assert run.ephemeral is False
        assert run.path == repo

    assert "downgraded to in-place" in caplog.text
    assert "test-cloud" in caplog.text


def test_skill_wires_ephemeral_flags_to_the_canonical_helper() -> None:
    skill = (REPO_ROOT / "skills" / "validate-feature" / "SKILL.md").read_text()

    assert "`--ephemeral` —" in skill
    assert "`--include-dirty` —" in skill
    assert "from validation_worktree import validation_worktree" in skill
    assert '"<skill-base-dir>/scripts/validation_worktree.py"' in skill
    assert "VALIDATION_VALIDATED_COMMIT" in skill
    assert "VALIDATION_VALIDATED_TREE" in skill
