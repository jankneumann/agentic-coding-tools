"""Tests for merge_worktrees.py — merge protocol for worktree branches."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from merge_worktrees import merge_packages, format_human, main  # noqa: E402


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _git_stdout(cwd: Path, *args: str) -> str:
    return _git(cwd, *args).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with an initial commit on main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", "main")
    return repo


def _create_package_branch(
    repo: Path,
    change_id: str,
    package_id: str,
    files: dict[str, str],
) -> None:
    """Create a package branch with the given file changes."""
    branch = f"openspec/{change_id}--{package_id}"
    _git(repo, "checkout", "-b", branch, "main")
    for name, content in files.items():
        filepath = repo / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        _git(repo, "add", name)
    _git(repo, "commit", "-m", f"changes for {package_id}")
    _git(repo, "checkout", "main")


def _create_feature_branch(repo: Path, change_id: str) -> None:
    """Create the feature branch from main."""
    branch = f"openspec/{change_id}"
    _git(repo, "checkout", "-b", branch, "main")
    _git(repo, "checkout", "main")


# ---------------------------------------------------------------------------
# Tests: successful merges
# ---------------------------------------------------------------------------

class TestSuccessfulMerge:
    def test_merge_single_package(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        change_id = "test-feature"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-backend", {
            "src/backend.py": "print('backend')\n",
        })

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-backend"],
            cwd=str(repo),
        )

        assert result["success"] is True
        assert result["change_id"] == change_id
        assert result["feature_branch"] == f"openspec/{change_id}"
        assert result["merged"] == ["wp-backend"]
        assert result["conflicts"] == []
        # Verify the file exists on the feature branch
        _git(repo, "checkout", f"openspec/{change_id}")
        assert (repo / "src" / "backend.py").exists()

    def test_merge_multiple_packages(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        change_id = "multi-pkg"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-backend", {
            "src/backend.py": "print('backend')\n",
        })
        _create_package_branch(repo, change_id, "wp-frontend", {
            "src/frontend.js": "console.log('frontend');\n",
        })

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-backend", "wp-frontend"],
            cwd=str(repo),
        )

        assert result["success"] is True
        assert result["merged"] == ["wp-backend", "wp-frontend"]
        assert result["conflicts"] == []
        # Verify both files exist
        _git(repo, "checkout", f"openspec/{change_id}")
        assert (repo / "src" / "backend.py").exists()
        assert (repo / "src" / "frontend.js").exists()

    def test_merge_preserves_order(self, tmp_path: Path) -> None:
        """Packages are merged in the order provided."""
        repo = _init_repo(tmp_path)
        change_id = "order-test"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-alpha", {
            "alpha.txt": "alpha\n",
        })
        _create_package_branch(repo, change_id, "wp-beta", {
            "beta.txt": "beta\n",
        })

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-alpha", "wp-beta"],
            cwd=str(repo),
        )

        assert result["merged"] == ["wp-alpha", "wp-beta"]

        # Check git log for merge commit order
        _git(repo, "checkout", f"openspec/{change_id}")
        log = _git_stdout(repo, "log", "--oneline", "--merges")
        lines = log.splitlines()
        # Most recent merge is first in log
        assert "wp-beta" in lines[0]
        assert "wp-alpha" in lines[1]


# ---------------------------------------------------------------------------
# Tests: conflict detection
# ---------------------------------------------------------------------------

class TestConflictDetection:
    def test_conflict_detected_and_aborted(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        change_id = "conflict-test"

        # Create feature branch with a change to shared.py
        feat_branch = f"openspec/{change_id}"
        _git(repo, "checkout", "-b", feat_branch, "main")
        (repo / "shared.py").write_text("feature version\n")
        _git(repo, "add", "shared.py")
        _git(repo, "commit", "-m", "feature change to shared.py")
        _git(repo, "checkout", "main")

        # Create package branch with conflicting change
        pkg_branch = f"openspec/{change_id}--wp-tests"
        _git(repo, "checkout", "-b", pkg_branch, "main")
        (repo / "shared.py").write_text("package version\n")
        _git(repo, "add", "shared.py")
        _git(repo, "commit", "-m", "package change to shared.py")
        _git(repo, "checkout", "main")

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-tests"],
            cwd=str(repo),
        )

        assert result["success"] is False
        assert result["merged"] == []
        assert len(result["conflicts"]) == 1
        conflict = result["conflicts"][0]
        assert conflict["package"] == "wp-tests"
        assert conflict["branch"] == pkg_branch
        assert "shared.py" in conflict["files"]
        assert conflict["error"]  # non-empty error message

    def test_partial_conflict(self, tmp_path: Path) -> None:
        """First package merges, second conflicts."""
        repo = _init_repo(tmp_path)
        change_id = "partial"

        # Feature branch with a change
        feat_branch = f"openspec/{change_id}"
        _git(repo, "checkout", "-b", feat_branch, "main")
        (repo / "shared.py").write_text("feature version\n")
        _git(repo, "add", "shared.py")
        _git(repo, "commit", "-m", "feature change")
        _git(repo, "checkout", "main")

        # Clean package (no conflict)
        _create_package_branch(repo, change_id, "wp-clean", {
            "clean.py": "no conflict\n",
        })

        # Conflicting package
        pkg_branch = f"openspec/{change_id}--wp-conflict"
        _git(repo, "checkout", "-b", pkg_branch, "main")
        (repo / "shared.py").write_text("conflicting version\n")
        _git(repo, "add", "shared.py")
        _git(repo, "commit", "-m", "conflicting change")
        _git(repo, "checkout", "main")

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-clean", "wp-conflict"],
            cwd=str(repo),
        )

        assert result["success"] is False
        assert result["merged"] == ["wp-clean"]
        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["package"] == "wp-conflict"

    def test_nonexistent_branch(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        change_id = "no-branch"
        _create_feature_branch(repo, change_id)

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-missing"],
            cwd=str(repo),
        )

        assert result["success"] is False
        assert len(result["conflicts"]) == 1
        assert "does not exist" in result["conflicts"][0]["error"]


# ---------------------------------------------------------------------------
# Tests: dry-run mode
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_no_persist(self, tmp_path: Path) -> None:
        """Dry-run merges do not persist on the feature branch."""
        repo = _init_repo(tmp_path)
        change_id = "dry-run"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-backend", {
            "src/backend.py": "print('backend')\n",
        })

        # Record the commit before merge
        _git(repo, "checkout", f"openspec/{change_id}")
        commit_before = _git_stdout(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "main")

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-backend"],
            cwd=str(repo),
            dry_run=True,
        )

        assert result["success"] is True
        assert result["merged"] == ["wp-backend"]

        # Verify no new commits were made
        _git(repo, "checkout", f"openspec/{change_id}")
        commit_after = _git_stdout(repo, "rev-parse", "HEAD")
        assert commit_before == commit_after
        # File should not exist
        assert not (repo / "src" / "backend.py").exists()

    def test_dry_run_detects_conflict(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        change_id = "dry-conflict"

        feat_branch = f"openspec/{change_id}"
        _git(repo, "checkout", "-b", feat_branch, "main")
        (repo / "shared.py").write_text("feature version\n")
        _git(repo, "add", "shared.py")
        _git(repo, "commit", "-m", "feature change")
        _git(repo, "checkout", "main")

        pkg_branch = f"openspec/{change_id}--wp-tests"
        _git(repo, "checkout", "-b", pkg_branch, "main")
        (repo / "shared.py").write_text("package version\n")
        _git(repo, "add", "shared.py")
        _git(repo, "commit", "-m", "package change")
        _git(repo, "checkout", "main")

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-tests"],
            cwd=str(repo),
            dry_run=True,
        )

        assert result["success"] is False
        assert len(result["conflicts"]) == 1

    def test_dry_run_multiple_all_clean(self, tmp_path: Path) -> None:
        """Dry-run with multiple non-conflicting packages."""
        repo = _init_repo(tmp_path)
        change_id = "dry-multi"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-a", {"a.txt": "a\n"})
        _create_package_branch(repo, change_id, "wp-b", {"b.txt": "b\n"})

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-a", "wp-b"],
            cwd=str(repo),
            dry_run=True,
        )

        assert result["success"] is True
        assert result["merged"] == ["wp-a", "wp-b"]


# ---------------------------------------------------------------------------
# Tests: JSON output format
# ---------------------------------------------------------------------------

class TestJsonOutput:
    def test_json_structure(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        change_id = "json-test"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-api", {
            "api.py": "pass\n",
        })

        result = merge_packages(
            change_id=change_id,
            package_ids=["wp-api"],
            cwd=str(repo),
        )

        # Verify all expected keys
        assert "success" in result
        assert "change_id" in result
        assert "feature_branch" in result
        assert "merged" in result
        assert "conflicts" in result

        # Verify JSON serializable
        serialized = json.dumps(result)
        parsed = json.loads(serialized)
        assert parsed == result


# ---------------------------------------------------------------------------
# Tests: CLI via main()
# ---------------------------------------------------------------------------

class TestCLI:
    def test_main_success_exit_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _init_repo(tmp_path)
        change_id = "cli-test"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-core", {
            "core.py": "pass\n",
        })

        monkeypatch.chdir(repo)
        exit_code = main(["cli-test", "wp-core", "--json"])
        assert exit_code == 0

    def test_main_conflict_exit_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _init_repo(tmp_path)
        change_id = "cli-fail"
        _create_feature_branch(repo, change_id)
        # No package branch created — will fail with "does not exist"

        monkeypatch.chdir(repo)
        exit_code = main(["cli-fail", "wp-missing", "--json"])
        assert exit_code == 1

    def test_main_dry_run_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _init_repo(tmp_path)
        change_id = "cli-dry"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-x", {"x.txt": "x\n"})

        monkeypatch.chdir(repo)
        exit_code = main(["cli-dry", "wp-x", "--dry-run", "--json"])
        assert exit_code == 0

    def test_main_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _init_repo(tmp_path)
        change_id = "cli-json"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-out", {"out.txt": "out\n"})

        monkeypatch.chdir(repo)
        main(["cli-json", "wp-out", "--json"])

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["merged"] == ["wp-out"]

    def test_main_human_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _init_repo(tmp_path)
        change_id = "cli-human"
        _create_feature_branch(repo, change_id)
        _create_package_branch(repo, change_id, "wp-h", {"h.txt": "h\n"})

        monkeypatch.chdir(repo)
        main(["cli-human", "wp-h"])

        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out
        assert "wp-h" in captured.out


# ---------------------------------------------------------------------------
# Tests: human-readable formatting
# ---------------------------------------------------------------------------

class TestFormatHuman:
    def test_success_format(self) -> None:
        result = {
            "success": True,
            "change_id": "test",
            "feature_branch": "openspec/test",
            "merged": ["wp-a", "wp-b"],
            "conflicts": [],
        }
        output = format_human(result)
        assert "SUCCESS" in output
        assert "wp-a" in output
        assert "wp-b" in output

    def test_failure_format(self) -> None:
        result = {
            "success": False,
            "change_id": "test",
            "feature_branch": "openspec/test",
            "merged": ["wp-a"],
            "conflicts": [{
                "package": "wp-b",
                "branch": "openspec/test--wp-b",
                "files": ["shared.py"],
                "error": "Merge conflict in shared.py",
            }],
        }
        output = format_human(result)
        assert "FAILED" in output
        assert "wp-a" in output
        assert "wp-b" in output
        assert "shared.py" in output
        assert "Merge conflict" in output
