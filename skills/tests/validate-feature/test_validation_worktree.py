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
    UnsafeValidationPathError,
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
        (scratch_change / "architecture-impact.md").write_text("impact\n")
        (run.path / "deploy-residue.log").write_text("discard me\n")
        scratch = run.path

    findings = json.loads((change_dir / "validation-findings.json").read_text())
    assert findings["validated_commit"] == run.validated_commit
    assert findings["validated_tree"] == run.validated_tree
    report = (change_dir / "validation-report.md").read_text()
    assert f"**Validated commit**: {run.validated_commit}" in report
    assert f"**Validated tree**: {run.validated_tree}" in report
    assert (change_dir / "architecture-impact.md").read_text() == "impact\n"
    assert not (repo / "deploy-residue.log").exists()
    assert not scratch.exists()


def test_scratch_is_removed_when_validation_raises(repo: Path) -> None:
    with pytest.raises(RuntimeError, match="validation failed"):
        with validation_worktree(repo, "example") as run:
            scratch = run.path
            raise RuntimeError("validation failed")

    assert not scratch.exists()


def test_exception_does_not_restamp_unchanged_preexisting_artifacts(repo: Path) -> None:
    change_dir = repo / "openspec" / "changes" / "example"
    change_dir.mkdir(parents=True)
    report = change_dir / "validation-report.md"
    findings = change_dir / "validation-findings.json"
    report.write_text("# stale report\n\n**PASS**\n")
    findings.write_text('{"result": "stale-pass"}\n')
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add stale validation artifacts")

    with pytest.raises(RuntimeError, match="validation failed"):
        with validation_worktree(repo, "example"):
            raise RuntimeError("validation failed")

    assert report.read_text() == "# stale report\n\n**PASS**\n"
    assert findings.read_text() == '{"result": "stale-pass"}\n'


def test_cli_nonzero_persists_a_new_failure_report_but_not_stale_findings(
    repo: Path,
) -> None:
    change_dir = repo / "openspec" / "changes" / "example"
    change_dir.mkdir(parents=True)
    findings = change_dir / "validation-findings.json"
    findings.write_text('{"result": "stale-pass"}\n')
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add stale findings")

    child = (
        "from pathlib import Path; "
        "p=Path('openspec/changes/example'); "
        "p.mkdir(parents=True, exist_ok=True); "
        "(p/'validation-report.md').write_text('# Validation\\n\\n**FAIL**\\n'); "
        "raise SystemExit(7)"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "validation_worktree.py"),
            "--source",
            str(repo),
            "--change-id",
            "example",
            "--",
            sys.executable,
            "-c",
            child,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 7, result.stderr
    report = (change_dir / "validation-report.md").read_text()
    assert "**FAIL**" in report
    assert "**Validated commit**:" in report
    assert findings.read_text() == '{"result": "stale-pass"}\n'


def test_cloud_harness_downgrades_to_in_place(repo: Path, caplog: pytest.LogCaptureFixture) -> None:
    class CloudProfile:
        isolation_provided = True
        source = "test-cloud"

    with validation_worktree(repo, "example", detector=lambda: CloudProfile()) as run:
        assert run.ephemeral is False
        assert run.path == repo

    assert "downgraded to in-place" in caplog.text
    assert "test-cloud" in caplog.text


def test_cloud_harness_still_refuses_dirty_source_without_opt_in(repo: Path) -> None:
    class CloudProfile:
        isolation_provided = True
        source = "test-cloud"

    (repo / "tracked.txt").write_text("dirty\n")

    with pytest.raises(DirtyValidationSourceError, match="--include-dirty"):
        with validation_worktree(repo, "example", detector=lambda: CloudProfile()):
            pass


def test_cloud_include_dirty_records_exact_tree_without_changing_source(repo: Path) -> None:
    class CloudProfile:
        isolation_provided = True
        source = "test-cloud"

    (repo / "tracked.txt").write_text("staged\n")
    _git(repo, "add", "tracked.txt")
    (repo / "other.txt").write_text("unstaged\n")
    (repo / "untracked.txt").write_text("untracked\n")
    status_before = _git(repo, "status", "--short")

    with validation_worktree(
        repo,
        "example",
        include_dirty=True,
        detector=lambda: CloudProfile(),
    ) as run:
        assert run.ephemeral is False
        assert run.validated_tree != _git(repo, "rev-parse", "HEAD^{tree}")

    assert _git(repo, "status", "--short") == status_before


def test_skill_wires_ephemeral_flags_to_the_canonical_helper() -> None:
    skill = (REPO_ROOT / "skills" / "validate-feature" / "SKILL.md").read_text()

    assert "`--ephemeral` —" in skill
    assert "`--include-dirty` —" in skill
    assert '"$VALIDATION_HELPER" prepare' in skill
    assert '"$VALIDATION_HELPER" finalize' in skill
    assert '"<skill-base-dir>/scripts/validation_worktree.py"' in skill
    assert "VALIDATION_VALIDATED_COMMIT" in skill
    assert "VALIDATION_VALIDATED_TREE" in skill
    assert "<validation-driver-command>" not in skill


@pytest.mark.parametrize(
    "change_id",
    ["../escape", "a/escape", "..", "a..b", "", " space", "é"],
)
def test_change_id_is_validated_before_paths_are_created(
    repo: Path,
    change_id: str,
) -> None:
    with pytest.raises(ValueError, match="invalid change_id"):
        with validation_worktree(repo, change_id):
            pass

    assert not (repo / ".git-worktrees" / ".validation").exists()


def test_change_directory_symlink_escape_is_rejected(repo: Path, tmp_path: Path) -> None:
    changes = repo / "openspec" / "changes"
    changes.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (changes / "example").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeValidationPathError, match="change directory"):
        with validation_worktree(repo, "example"):
            pass


def test_scratch_root_symlink_escape_is_rejected(repo: Path, tmp_path: Path) -> None:
    worktree_parent = repo / ".git-worktrees"
    worktree_parent.mkdir()
    outside = tmp_path / "outside-scratch"
    outside.mkdir()
    (worktree_parent / ".validation").symlink_to(outside, target_is_directory=True)
    _git(repo, "add", ".git-worktrees/.validation")
    _git(repo, "commit", "-m", "add unsafe scratch symlink")

    with pytest.raises(UnsafeValidationPathError, match="scratch root"):
        with validation_worktree(repo, "example"):
            pass

    assert list(outside.iterdir()) == []


def test_symlink_artifact_source_is_rejected_and_not_copied(repo: Path, tmp_path: Path) -> None:
    change_dir = repo / "openspec" / "changes" / "example"
    change_dir.mkdir(parents=True)
    (change_dir / ".gitkeep").write_text("")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add change")
    outside = tmp_path / "outside-report"
    outside.write_text("outside\n")

    with pytest.raises(UnsafeValidationPathError, match="symlink artifact"):
        with validation_worktree(repo, "example") as run:
            scratch_change = run.path / "openspec" / "changes" / "example"
            (scratch_change / "validation-report.md").symlink_to(outside)

    assert outside.read_text() == "outside\n"
    assert not (change_dir / "validation-report.md").exists()


def test_symlink_artifact_destination_is_rejected(repo: Path, tmp_path: Path) -> None:
    change_dir = repo / "openspec" / "changes" / "example"
    change_dir.mkdir(parents=True)
    outside = tmp_path / "outside-report"
    outside.write_text("outside\n")
    (change_dir / "validation-report.md").symlink_to(outside)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add symlink report")

    with pytest.raises(UnsafeValidationPathError, match="symlink artifact"):
        with validation_worktree(repo, "example"):
            pass

    assert outside.read_text() == "outside\n"


def test_identity_rendering_replaces_an_unpaired_tree_line(repo: Path) -> None:
    change_dir = repo / "openspec" / "changes" / "example"
    change_dir.mkdir(parents=True)
    (change_dir / ".gitkeep").write_text("")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add change")

    with validation_worktree(repo, "example") as run:
        report = run.path / "openspec" / "changes" / "example" / "validation-report.md"
        report.write_text("**Validated tree**: stale\n# Validation\n")

    rendered = (change_dir / "validation-report.md").read_text()
    assert rendered.count("**Validated tree**:") == 1
    assert rendered.count("**Validated commit**:") == 1


def test_prepare_finalize_cli_is_an_end_to_end_ephemeral_path(repo: Path) -> None:
    change_dir = repo / "openspec" / "changes" / "example"
    change_dir.mkdir(parents=True)
    (change_dir / ".gitkeep").write_text("")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add change")
    state_file = repo.parent / "validation-state.json"
    script = str(SCRIPTS / "validation_worktree.py")

    prepared = subprocess.run(
        [
            sys.executable,
            script,
            "prepare",
            "--source",
            str(repo),
            "--change-id",
            "example",
            "--state-file",
            str(state_file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    state = json.loads(prepared.stdout)
    scratch = Path(state["path"])
    scratch_change = scratch / "openspec" / "changes" / "example"
    (scratch_change / "validation-report.md").write_text("# PASS\n")
    (scratch_change / "architecture-impact.md").write_text("# Impact\n")

    subprocess.run(
        [sys.executable, script, "finalize", "--state-file", str(state_file)],
        capture_output=True,
        text=True,
        check=True,
    )

    assert not scratch.exists()
    assert not state_file.exists()
    assert "# PASS" in (change_dir / "validation-report.md").read_text()
    assert (change_dir / "architecture-impact.md").read_text() == "# Impact\n"
