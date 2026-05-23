"""Tests for skills/review-artifacts/scripts/open_artifacts.py.

Exercises the pure discovery functions (no subprocess). The `code` CLI
invocation is covered indirectly via dry-run mode.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Load the module via importlib to avoid relying on PYTHONPATH gymnastics.
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "review-artifacts"
    / "scripts"
    / "open_artifacts.py"
)
_spec = importlib.util.spec_from_file_location("open_artifacts", _SCRIPT_PATH)
assert _spec and _spec.loader
open_artifacts = importlib.util.module_from_spec(_spec)
sys.modules["open_artifacts"] = open_artifacts
_spec.loader.exec_module(open_artifacts)


# ---------------------------------------------------------------------------
# Fixture: synthetic repo with an openspec change directory
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Build a minimal repo: openspec change dir, work-packages.yaml, code files."""
    # Initialize a git repo so _git_toplevel returns this directory.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=tmp_path, check=True
    )
    # Some git configurations require commit.gpgsign=false in CI fixtures.
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True
    )

    # Create the OpenSpec change skeleton
    change_dir = tmp_path / "openspec" / "changes" / "add-test-thing"
    (change_dir / "specs" / "test-capability").mkdir(parents=True)
    (change_dir / "contracts").mkdir()
    (change_dir / "proposal.md").write_text("# proposal", encoding="utf-8")
    (change_dir / "design.md").write_text("# design", encoding="utf-8")
    (change_dir / "tasks.md").write_text("# tasks", encoding="utf-8")
    (change_dir / "specs" / "test-capability" / "spec.md").write_text(
        "## ADDED Requirements", encoding="utf-8"
    )
    (change_dir / "contracts" / "README.md").write_text("# contracts", encoding="utf-8")
    (change_dir / "work-packages.yaml").write_text(
        """\
schema_version: 1
feature:
  id: add-test-thing
  plan_revision: 1
contracts:
  revision: 1
  openapi:
    primary: "contracts/README.md"
    files:
      - "contracts/README.md"
packages:
  - package_id: wp-only
    title: "Only package"
    task_type: implementation
    description: "Test"
    role: python-engineer
    priority: 4
    depends_on: []
    timeout_minutes: 30
    retry_budget: 1
    min_trust_level: 2
    scope:
      write_allow:
        - "agent-coordinator/scripts/seed_kanban_board.py"
        - "apps/kanban-viz/src/**/*.tsx"
        - "openspec/changes/add-test-thing/proposal.md"
      read_allow:
        - "agent-coordinator/**"
""",
        encoding="utf-8",
    )

    # Create the files that scope.write_allow patterns match
    (tmp_path / "agent-coordinator" / "scripts").mkdir(parents=True)
    (tmp_path / "agent-coordinator" / "scripts" / "seed_kanban_board.py").write_text(
        "# stub", encoding="utf-8"
    )
    (tmp_path / "apps" / "kanban-viz" / "src" / "App.tsx").mkdir(parents=True)
    # Whoops — mkdir creates the App.tsx as a directory. Rebuild.
    import shutil
    shutil.rmtree(tmp_path / "apps")
    (tmp_path / "apps" / "kanban-viz" / "src").mkdir(parents=True)
    (tmp_path / "apps" / "kanban-viz" / "src" / "App.tsx").write_text(
        "// stub", encoding="utf-8"
    )
    (tmp_path / "apps" / "kanban-viz" / "src" / "lib").mkdir()
    (tmp_path / "apps" / "kanban-viz" / "src" / "lib" / "runtime.tsx").write_text(
        "// stub2", encoding="utf-8"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# discover_change_artifacts — curated read-order
# ---------------------------------------------------------------------------


def test_discover_change_artifacts_read_order(fake_repo: Path) -> None:
    """Files come back in proposal → design → tasks → specs → wp → contracts order."""
    files = open_artifacts.discover_change_artifacts(
        "add-test-thing", fake_repo, include_scope=False
    )
    names = [f.name for f in files]
    # Curated order must hold
    assert names == [
        "proposal.md",
        "design.md",
        "tasks.md",
        "spec.md",  # under specs/test-capability/
        "work-packages.yaml",
        "README.md",  # under contracts/
    ]


def test_discover_change_artifacts_with_scope(fake_repo: Path) -> None:
    """include_scope=True appends scope.write_allow files (deduped, glob-expanded)."""
    files = open_artifacts.discover_change_artifacts(
        "add-test-thing", fake_repo, include_scope=True
    )
    rels = [f.relative_to(fake_repo).as_posix() for f in files]

    # Proposal artifacts come first
    assert rels[0] == "openspec/changes/add-test-thing/proposal.md"
    # Implementation files appear after the proposal artifacts
    assert "agent-coordinator/scripts/seed_kanban_board.py" in rels
    assert "apps/kanban-viz/src/App.tsx" in rels
    assert "apps/kanban-viz/src/lib/runtime.tsx" in rels
    # The scope entry that points at the proposal.md must NOT duplicate
    # (it was already opened in step 1)
    assert rels.count("openspec/changes/add-test-thing/proposal.md") == 1


def test_discover_change_artifacts_missing_change_id(fake_repo: Path) -> None:
    """Unknown change-id returns empty list, not an exception."""
    files = open_artifacts.discover_change_artifacts(
        "does-not-exist", fake_repo, include_scope=True
    )
    assert files == []


def test_discover_change_artifacts_archive_fallback(fake_repo: Path) -> None:
    """If only an archive entry exists, the resolver finds it."""
    # Move active dir into archive
    archive = fake_repo / "openspec" / "changes" / "archive"
    archive.mkdir(parents=True)
    src = fake_repo / "openspec" / "changes" / "add-test-thing"
    dst = archive / "2026-05-23-add-test-thing"
    src.rename(dst)

    files = open_artifacts.discover_change_artifacts(
        "add-test-thing", fake_repo, include_scope=False
    )
    assert files, "archive entry should be found"
    assert files[0].name == "proposal.md"
    assert "2026-05-23-add-test-thing" in str(files[0])


# ---------------------------------------------------------------------------
# discover_git_changes
# ---------------------------------------------------------------------------


def test_discover_git_changes_picks_up_uncommitted(fake_repo: Path) -> None:
    """Files modified in the working tree show up via git status --porcelain."""
    # Initial commit to give us a HEAD
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "branch", "-M", "main"], cwd=fake_repo, check=True
    )

    # Modify a file (working tree dirty)
    target = fake_repo / "openspec" / "changes" / "add-test-thing" / "proposal.md"
    target.write_text("# proposal (updated)", encoding="utf-8")

    files = open_artifacts.discover_git_changes(fake_repo, base="main")
    rels = [f.relative_to(fake_repo).as_posix() for f in files]
    assert "openspec/changes/add-test-thing/proposal.md" in rels


def test_discover_git_changes_branch_local_commits(fake_repo: Path) -> None:
    """Files committed on a feature branch (not on main) show up."""
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "branch", "-M", "main"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "feature-branch"],
        cwd=fake_repo,
        check=True,
    )

    new_file = fake_repo / "agent-coordinator" / "scripts" / "new_thing.py"
    new_file.write_text("# new", encoding="utf-8")
    subprocess.run(["git", "add", str(new_file)], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "add new_thing"], cwd=fake_repo, check=True
    )

    files = open_artifacts.discover_git_changes(fake_repo, base="main")
    rels = [f.relative_to(fake_repo).as_posix() for f in files]
    assert "agent-coordinator/scripts/new_thing.py" in rels


def test_discover_git_changes_uncommitted_first(fake_repo: Path) -> None:
    """Uncommitted changes are listed before branch-local commits."""
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "branch", "-M", "main"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "feature-branch"],
        cwd=fake_repo,
        check=True,
    )

    # Commit one file on the branch
    committed = fake_repo / "agent-coordinator" / "scripts" / "committed.py"
    committed.write_text("# committed", encoding="utf-8")
    subprocess.run(["git", "add", str(committed)], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "committed file"],
        cwd=fake_repo,
        check=True,
    )

    # Make an unrelated working-tree change
    uncommitted = fake_repo / "openspec" / "changes" / "add-test-thing" / "tasks.md"
    uncommitted.write_text("# tasks (modified)", encoding="utf-8")

    files = open_artifacts.discover_git_changes(fake_repo, base="main")
    rels = [f.relative_to(fake_repo).as_posix() for f in files]

    idx_uncommitted = rels.index("openspec/changes/add-test-thing/tasks.md")
    idx_committed = rels.index("agent-coordinator/scripts/committed.py")
    assert idx_uncommitted < idx_committed, (
        f"uncommitted should come before committed; got order: {rels}"
    )


# ---------------------------------------------------------------------------
# auto_detect_mode
# ---------------------------------------------------------------------------


def test_auto_detect_picks_change_id_for_openspec_branch(fake_repo: Path) -> None:
    """When on `openspec/<id>` branch with matching change-dir, picks change-id mode."""
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "openspec/add-test-thing"],
        cwd=fake_repo,
        check=True,
    )

    mode, payload = open_artifacts.auto_detect_mode(fake_repo)
    assert mode == "change-id"
    assert payload == "add-test-thing"


def test_auto_detect_falls_back_to_git_changes_on_non_openspec_branch(
    fake_repo: Path,
) -> None:
    """When not on an openspec branch, fallback is git-changes."""
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=fake_repo, check=True
    )
    # Stay on default branch (main / master)
    mode, payload = open_artifacts.auto_detect_mode(fake_repo)
    assert mode == "git-changes"
    assert payload is None


def test_auto_detect_handles_parallel_agent_branch_suffix(fake_repo: Path) -> None:
    """`openspec/<id>--<agent-id>` should strip the --<agent-id> suffix."""
    subprocess.run(["git", "add", "-A"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "openspec/add-test-thing--wp-only"],
        cwd=fake_repo,
        check=True,
    )

    mode, payload = open_artifacts.auto_detect_mode(fake_repo)
    assert mode == "change-id"
    assert payload == "add-test-thing"


# ---------------------------------------------------------------------------
# main() integration — dry-run path (no `code` invocation)
# ---------------------------------------------------------------------------


def test_main_dry_run_default_uses_new_window(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end via main() — dry-run prints `code -n` (new window default)
    and returns 0.

    `-n` (not `-r`) is the safe default: opens a fresh window so the
    operator's existing VS Code work is untouched.
    """
    monkeypatch.chdir(fake_repo)
    rc = open_artifacts.main(
        ["--change-id", "add-test-thing", "--dry-run", "--no-scope"]
    )
    assert rc == 0
    out = capsys.readouterr()
    combined = out.out + out.err
    assert "code -n" in combined, (
        f"expected default to be `code -n` (new window); got: {combined!r}"
    )
    assert "code -r" not in combined, (
        "default must NOT use -r (reuse window) — it can displace open files"
    )
    assert "proposal.md" in combined
    assert "design.md" in combined


def test_main_dry_run_reuse_window_flag(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--reuse-window opts into the legacy `code -r` behavior."""
    monkeypatch.chdir(fake_repo)
    rc = open_artifacts.main(
        [
            "--change-id",
            "add-test-thing",
            "--dry-run",
            "--no-scope",
            "--reuse-window",
        ]
    )
    assert rc == 0
    out = capsys.readouterr()
    combined = out.out + out.err
    assert "code -r" in combined
    assert "code -n" not in combined


def test_main_missing_change_id_returns_1(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown change-id is a setup error (exit 1)."""
    monkeypatch.chdir(fake_repo)
    rc = open_artifacts.main(
        ["--change-id", "nonexistent-change", "--dry-run"]
    )
    assert rc == 1
