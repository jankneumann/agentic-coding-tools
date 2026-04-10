"""Tests for the git adapter layer (wp-contracts tasks 1.1, 1.2).

Covers:
  - Ref name / branch name regex validation (R7)
  - Injection prevention: semicolons, backticks, $(), newlines in branch names
  - MergeTreeResult shape per contracts/internal/git-adapter-api.yaml
  - SubprocessGitAdapter integration via monkeypatched subprocess.run
  - Git version check (MIN_GIT_VERSION = 2.38)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.git_adapter import (
    GitVersionError,
    InvalidRefNameError,
    SubprocessGitAdapter,
    _parse_conflict_files,
    parse_git_version,
    validate_branch_name,
    validate_speculative_ref_name,
)

# ---------------------------------------------------------------------------
# Regex validation tests (R7)
# ---------------------------------------------------------------------------


class TestSpeculativeRefValidation:
    """validate_speculative_ref_name: match R7 regex, reject injection attempts."""

    def test_valid_ref(self) -> None:
        validate_speculative_ref_name("refs/speculative/train-abcd1234/pos-1")
        validate_speculative_ref_name("refs/speculative/train-abcdef0123456789/pos-99")
        validate_speculative_ref_name("refs/speculative/train-abcdefab/pos-1234")

    @pytest.mark.parametrize(
        "bad_ref",
        [
            "refs/heads/main",  # Wrong prefix
            "refs/speculative/pos-1",  # No train id
            "refs/speculative/train-xyz/pos-1",  # Non-hex train id
            "refs/speculative/train-abcdefg/pos-1",  # Train id too short (<8)
            "refs/speculative/train-abcd1234/pos-abc",  # Non-numeric position
            "refs/speculative/train-abcd1234/pos-12345",  # Position > 4 digits
            "refs/speculative/train-abcd1234",  # Missing /pos-N
            "",
        ],
    )
    def test_invalid_ref(self, bad_ref: str) -> None:
        with pytest.raises(InvalidRefNameError):
            validate_speculative_ref_name(bad_ref)

    def test_null_byte_rejected(self) -> None:
        with pytest.raises(InvalidRefNameError, match="null byte"):
            validate_speculative_ref_name("refs/speculative/train-abcd1234\x00/pos-1")

    def test_non_string_rejected(self) -> None:
        with pytest.raises(InvalidRefNameError, match="must be str"):
            validate_speculative_ref_name(42)  # type: ignore[arg-type]


class TestBranchNameValidation:
    """validate_branch_name: R7 injection prevention test cases."""

    @pytest.mark.parametrize(
        "good_branch",
        [
            "main",
            "openspec/speculative-merge-trains",
            "feature/wp-contracts",
            "release-1.2.3",
            "users/alice/experiment",
            "a" * 200,
        ],
    )
    def test_valid_branch(self, good_branch: str) -> None:
        validate_branch_name(good_branch)

    @pytest.mark.parametrize(
        "bad_branch",
        [
            "main;rm -rf /",  # Semicolon
            "main`whoami`",  # Backtick
            "main$(pwd)",  # Command substitution
            "main\nmain2",  # Newline
            "main|cat",  # Pipe
            "main&amp",  # Ampersand
            'main"foo"',  # Quotes
            "main>out",  # Redirection
            "a" * 201,  # Exceeds length limit
            "",  # Empty
            "main\x00null",  # Null byte
        ],
    )
    def test_injection_prevention(self, bad_branch: str) -> None:
        with pytest.raises(InvalidRefNameError):
            validate_branch_name(bad_branch)


# ---------------------------------------------------------------------------
# parse_git_version / _parse_conflict_files
# ---------------------------------------------------------------------------


class TestGitVersionParsing:
    def test_standard_output(self) -> None:
        assert parse_git_version("git version 2.39.2\n") == (2, 39)

    def test_windows_variant(self) -> None:
        assert parse_git_version("git version 2.40.1.windows.1") == (2, 40)

    def test_unparseable(self) -> None:
        with pytest.raises(GitVersionError):
            parse_git_version("not a version string")


class TestConflictFileParsing:
    def test_detects_conflict_in_stdout(self) -> None:
        output = "CONFLICT (content): Merge conflict in src/users.py\n"
        files = _parse_conflict_files(output, "")
        assert files == ["src/users.py"]

    def test_multiple_conflicts_sorted(self) -> None:
        output = (
            "CONFLICT (content): Merge conflict in src/b.py\n"
            "CONFLICT (content): Merge conflict in src/a.py\n"
        )
        files = _parse_conflict_files(output, "")
        assert files == ["src/a.py", "src/b.py"]

    def test_clean_merge(self) -> None:
        assert _parse_conflict_files("abc123\n", "") == []


# ---------------------------------------------------------------------------
# SubprocessGitAdapter — mocked subprocess.run
# ---------------------------------------------------------------------------


@dataclass
class _FakeCompleted:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


class TestSubprocessGitAdapterValidation:
    """Validation happens BEFORE subprocess — no git call should be made."""

    def test_create_speculative_ref_rejects_bad_branch(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)
        with patch("src.git_adapter.subprocess.run") as run_mock:
            with pytest.raises(InvalidRefNameError):
                adapter.create_speculative_ref(
                    base_ref="main",
                    feature_branch="main;rm -rf /",
                    ref_name="refs/speculative/train-abcd1234/pos-1",
                )
            run_mock.assert_not_called()

    def test_create_speculative_ref_rejects_bad_ref_name(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)
        with patch("src.git_adapter.subprocess.run") as run_mock:
            with pytest.raises(InvalidRefNameError):
                adapter.create_speculative_ref(
                    base_ref="main",
                    feature_branch="feature/x",
                    ref_name="refs/heads/main",  # Wrong prefix
                )
            run_mock.assert_not_called()

    def test_delete_speculative_refs_rejects_bad_train_id(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)
        with patch("src.git_adapter.subprocess.run") as run_mock:
            with pytest.raises(InvalidRefNameError):
                adapter.delete_speculative_refs("not-hex")
            run_mock.assert_not_called()


class TestSubprocessGitAdapterCreate:
    """Simulate subprocess.run to verify the success/conflict/error branches."""

    def _mk_adapter_with_version(self, tmp_repo: Path) -> SubprocessGitAdapter:
        adapter = SubprocessGitAdapter(tmp_repo)
        adapter._version_checked = True  # Skip version probe
        return adapter

    def test_success_returns_tree_oid_and_commit_sha(self, tmp_repo: Path) -> None:
        adapter = self._mk_adapter_with_version(tmp_repo)
        tree_oid = "a" * 40
        commit_sha = "b" * 40

        def fake_run(args: list[str], **kwargs: Any) -> _FakeCompleted:
            # args[0] is "git", args[1] is the subcommand
            cmd = args[1]
            if cmd == "merge-tree":
                return _FakeCompleted(returncode=0, stdout=f"{tree_oid}\n")
            if cmd == "commit-tree":
                return _FakeCompleted(returncode=0, stdout=f"{commit_sha}\n")
            if cmd == "update-ref":
                return _FakeCompleted(returncode=0)
            raise AssertionError(f"unexpected git subcommand: {cmd}")

        with patch("src.git_adapter.subprocess.run", side_effect=fake_run):
            result = adapter.create_speculative_ref(
                base_ref="main",
                feature_branch="feature/x",
                ref_name="refs/speculative/train-abcd1234/pos-1",
            )

        assert result.success is True
        assert result.tree_oid == tree_oid
        assert result.commit_sha == commit_sha
        assert result.conflict_files == []
        assert result.error is None

    def test_conflict_returns_conflict_files_not_error(self, tmp_repo: Path) -> None:
        adapter = self._mk_adapter_with_version(tmp_repo)

        def fake_run(args: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(
                returncode=1,
                stdout="CONFLICT (content): Merge conflict in src/users.py\n",
            )

        with patch("src.git_adapter.subprocess.run", side_effect=fake_run):
            result = adapter.create_speculative_ref(
                base_ref="main",
                feature_branch="feature/x",
                ref_name="refs/speculative/train-abcd1234/pos-1",
            )

        assert result.success is False
        assert result.conflict_files == ["src/users.py"]
        assert result.error is None  # Conflicts are NOT errors per contract
        assert result.tree_oid is None
        assert result.commit_sha is None

    def test_non_conflict_error_populates_error_field(self, tmp_repo: Path) -> None:
        adapter = self._mk_adapter_with_version(tmp_repo)

        def fake_run(args: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(
                returncode=128,  # git: fatal error
                stderr="fatal: not a git repository\n",
            )

        with patch("src.git_adapter.subprocess.run", side_effect=fake_run):
            result = adapter.create_speculative_ref(
                base_ref="main",
                feature_branch="feature/x",
                ref_name="refs/speculative/train-abcd1234/pos-1",
            )

        assert result.success is False
        assert "not a git repository" in (result.error or "")
        assert result.conflict_files == []

    def test_invalid_tree_oid_in_output(self, tmp_repo: Path) -> None:
        adapter = self._mk_adapter_with_version(tmp_repo)

        def fake_run(args: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(returncode=0, stdout="not-a-real-oid\n")

        with patch("src.git_adapter.subprocess.run", side_effect=fake_run):
            result = adapter.create_speculative_ref(
                base_ref="main",
                feature_branch="feature/x",
                ref_name="refs/speculative/train-abcd1234/pos-1",
            )

        assert result.success is False
        assert "invalid tree OID" in (result.error or "")


class TestSubprocessGitAdapterDelete:
    def test_delete_counts_refs(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)
        adapter._version_checked = True

        def fake_run(args: list[str], **kwargs: Any) -> _FakeCompleted:
            cmd = args[1]
            if cmd == "for-each-ref":
                return _FakeCompleted(
                    returncode=0,
                    stdout=(
                        "refs/speculative/train-abcd1234/pos-1\n"
                        "refs/speculative/train-abcd1234/pos-2\n"
                    ),
                )
            if cmd == "update-ref" and args[2] == "-d":
                return _FakeCompleted(returncode=0)
            raise AssertionError(f"unexpected: {args}")

        with patch("src.git_adapter.subprocess.run", side_effect=fake_run):
            count = adapter.delete_speculative_refs("abcd1234")
        assert count == 2


class TestSubprocessGitAdapterVersionCheck:
    def test_rejects_old_git(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)

        def fake_run(args: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(returncode=0, stdout="git version 2.30.0\n")

        with patch("src.git_adapter.subprocess.run", side_effect=fake_run):
            with pytest.raises(GitVersionError, match="2.38"):
                adapter._ensure_git_version()

    def test_accepts_new_git(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)

        def fake_run(args: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(returncode=0, stdout="git version 2.42.0\n")

        with patch("src.git_adapter.subprocess.run", side_effect=fake_run):
            adapter._ensure_git_version()  # Should not raise
        assert adapter._version_checked is True

    def test_missing_git_binary(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)
        with patch("src.git_adapter.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitVersionError, match="not found"):
                adapter._ensure_git_version()


# ---------------------------------------------------------------------------
# shell=False invariant (cannot be byped even by malicious input)
# ---------------------------------------------------------------------------


class TestShellFalseInvariant:
    """All subprocess.run calls must pass shell=False (or omit shell, which defaults to False)."""

    def test_run_always_uses_argument_list(self, tmp_repo: Path) -> None:
        adapter = SubprocessGitAdapter(tmp_repo)
        adapter._version_checked = True
        captured_calls: list[tuple[Any, dict[str, Any]]] = []

        def capture_run(args: Any, **kwargs: Any) -> _FakeCompleted:
            captured_calls.append((args, kwargs))
            return _FakeCompleted(returncode=0, stdout="a" * 40 + "\n")

        with patch("src.git_adapter.subprocess.run", side_effect=capture_run):
            adapter._run(["status"])

        assert len(captured_calls) == 1
        args, kwargs = captured_calls[0]
        assert isinstance(args, list), "Must use argument list, not string"
        assert kwargs.get("shell", False) is False
