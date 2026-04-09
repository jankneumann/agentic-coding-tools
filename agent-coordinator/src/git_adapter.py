"""Git adapter layer for speculative merge train operations.

The coordinator is historically git-agnostic — this module introduces a
`GitAdapter` protocol that the merge train service uses to create, delete,
and inspect speculative refs. An implementation (`SubprocessGitAdapter`)
shells out to `git` via `subprocess.run(..., shell=False)` exclusively.

Security model:
  - All ref names are validated against a strict regex BEFORE any subprocess
    call. Agent-supplied branch names are separately validated.
  - `subprocess.run` is always called with an argument list and `shell=False`.
    This prevents command injection even if validation is bypassed.
  - `InvalidRefNameError` is raised eagerly so that callers (and tests) can
    distinguish malformed input from git failures.

Contracts:
  - See `contracts/internal/git-adapter-api.yaml` for the canonical output
    shape of `create_speculative_ref` (success, tree_oid, commit_sha,
    conflict_files, error).
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation regexes and constants (Requirement R7)
# ---------------------------------------------------------------------------

#: Pattern for speculative ref names. `refs/speculative/train-<hex8..32>/pos-<digits>`
SPECULATIVE_REF_PATTERN = re.compile(r"^refs/speculative/train-[a-f0-9]{8,32}/pos-\d{1,4}$")

#: Pattern for agent-supplied branch names. No shell metacharacters, 1..200 chars.
BRANCH_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9/_.\-]{1,200}$")

#: Minimum git version required (for `git merge-tree --write-tree --messages`).
MIN_GIT_VERSION = (2, 38)

#: Time-to-live for speculative refs before watchdog GC, in hours (R7 scenario).
SPECULATIVE_REF_TTL_HOURS = 6


class InvalidRefNameError(ValueError):
    """Raised when a ref or branch name fails validation before subprocess spawn."""


class GitVersionError(RuntimeError):
    """Raised when the host `git` binary is older than MIN_GIT_VERSION."""


# ---------------------------------------------------------------------------
# Result dataclasses (mirror contracts/internal/git-adapter-api.yaml)
# ---------------------------------------------------------------------------


@dataclass
class MergeTreeResult:
    """Outcome of a `create_speculative_ref` operation.

    Field names match `contracts/internal/git-adapter-api.yaml#/create_speculative_ref`.
    """

    success: bool
    tree_oid: str | None = None
    commit_sha: str | None = None
    conflict_files: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class FastForwardResult:
    """Outcome of fast-forwarding a ref (e.g., main) to a target ref."""

    success: bool
    new_main_sha: str | None = None
    error: str | None = None


@dataclass
class ChangedFiles:
    """Result of get_changed_files between two refs."""

    changed_files: list[str] = field(default_factory=list)
    added_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GitAdapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class GitAdapter(Protocol):
    """Protocol for git operations used by the merge train service.

    Implementations must use `subprocess.run(args_list, shell=False)` only.
    """

    def create_speculative_ref(
        self,
        base_ref: str,
        feature_branch: str,
        ref_name: str,
    ) -> MergeTreeResult: ...

    def delete_speculative_refs(self, train_id: str) -> int: ...

    def fast_forward_main(self, speculative_ref: str) -> FastForwardResult: ...

    def get_changed_files(self, base_ref: str, feature_branch: str) -> ChangedFiles: ...

    def list_speculative_refs(self) -> list[str]: ...


# ---------------------------------------------------------------------------
# Validation helpers (used by SubprocessGitAdapter AND exposed for tests)
# ---------------------------------------------------------------------------


def validate_speculative_ref_name(ref_name: str) -> None:
    """Raise InvalidRefNameError if ref_name does not match SPECULATIVE_REF_PATTERN."""
    if not isinstance(ref_name, str):
        raise InvalidRefNameError(f"ref_name must be str, got {type(ref_name).__name__}")
    if "\x00" in ref_name:
        raise InvalidRefNameError("ref_name contains null byte")
    if len(ref_name) > 200:
        raise InvalidRefNameError(f"ref_name exceeds 200 chars: {len(ref_name)}")
    if not SPECULATIVE_REF_PATTERN.match(ref_name):
        raise InvalidRefNameError(
            f"ref_name does not match {SPECULATIVE_REF_PATTERN.pattern}: {ref_name!r}"
        )


def validate_branch_name(branch: str) -> None:
    """Raise InvalidRefNameError if branch has shell metacharacters or is out of bounds."""
    if not isinstance(branch, str):
        raise InvalidRefNameError(f"branch must be str, got {type(branch).__name__}")
    if "\x00" in branch:
        raise InvalidRefNameError("branch contains null byte")
    if not branch:
        raise InvalidRefNameError("branch must be non-empty")
    if len(branch) > 200:
        raise InvalidRefNameError(f"branch exceeds 200 chars: {len(branch)}")
    if not BRANCH_NAME_PATTERN.match(branch):
        raise InvalidRefNameError(
            f"branch contains disallowed characters: {branch!r}"
        )


def parse_git_version(version_output: str) -> tuple[int, int]:
    """Extract (major, minor) tuple from `git --version` output.

    Accepts strings like "git version 2.39.2" or "git version 2.40.1.windows.1".
    Raises GitVersionError if the format is unparseable.
    """
    match = re.search(r"git version (\d+)\.(\d+)", version_output)
    if not match:
        raise GitVersionError(f"could not parse git version from: {version_output!r}")
    return int(match.group(1)), int(match.group(2))


# ---------------------------------------------------------------------------
# SubprocessGitAdapter — real implementation
# ---------------------------------------------------------------------------


class SubprocessGitAdapter:
    """Concrete GitAdapter using `subprocess.run(args_list, shell=False)`.

    Performs a git version check on first use. The repo path is captured at
    construction time and used as `cwd` for every subprocess call.
    """

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)
        self._version_checked = False

    # ---- version check ----

    def _ensure_git_version(self) -> None:
        if self._version_checked:
            return
        try:
            result = subprocess.run(  # noqa: S603 — shell=False, explicit args
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise GitVersionError("git binary not found on PATH") from exc
        version = parse_git_version(result.stdout)
        if version < MIN_GIT_VERSION:
            raise GitVersionError(
                f"git {'.'.join(map(str, MIN_GIT_VERSION))} required, found "
                f"{'.'.join(map(str, version))}"
            )
        self._version_checked = True

    # ---- subprocess helper ----

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Run git with explicit args list, capturing stdout/stderr."""
        return subprocess.run(  # noqa: S603 — shell=False, explicit args
            ["git", *args],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )

    # ---- public methods ----

    def create_speculative_ref(
        self,
        base_ref: str,
        feature_branch: str,
        ref_name: str,
    ) -> MergeTreeResult:
        """Create a speculative ref by merging feature_branch onto base_ref.

        Uses `git merge-tree --write-tree --messages` (git 2.38+) which
        produces a tree OID on success or a conflict report on failure. On
        success, `git update-ref` points ref_name at a new commit whose tree
        is the merge result.

        Conflict detection is dual: (a) non-zero exit code from `git merge-tree`
        AND (b) parsing of `--messages` output for conflict markers. Either
        signal triggers conflict branch.
        """
        # Eager validation BEFORE any subprocess call.
        validate_branch_name(feature_branch)
        validate_speculative_ref_name(ref_name)
        # base_ref can be 'main', a SHA, or another speculative ref. Accept
        # either a speculative-ref pattern or a branch name pattern.
        if not (
            SPECULATIVE_REF_PATTERN.match(base_ref)
            or BRANCH_NAME_PATTERN.match(base_ref)
        ):
            raise InvalidRefNameError(f"base_ref invalid: {base_ref!r}")

        self._ensure_git_version()

        merge_tree = self._run(
            ["merge-tree", "--write-tree", "--messages", base_ref, feature_branch]
        )

        # Success path: exit 0, stdout has tree OID (first line), no conflict markers.
        conflict_files = _parse_conflict_files(merge_tree.stdout, merge_tree.stderr)
        if merge_tree.returncode != 0 or conflict_files:
            # Conflict (not an error)
            if merge_tree.returncode not in (0, 1):
                # returncode >= 2 typically means a non-conflict error
                return MergeTreeResult(
                    success=False,
                    error=(merge_tree.stderr or merge_tree.stdout or "").strip()
                    or "git merge-tree failed",
                )
            return MergeTreeResult(
                success=False,
                conflict_files=conflict_files,
            )

        # Extract the result tree OID (first line of stdout).
        stdout_lines = merge_tree.stdout.strip().splitlines()
        if not stdout_lines:
            return MergeTreeResult(success=False, error="merge-tree returned no tree OID")
        tree_oid = stdout_lines[0].strip()
        if not re.match(r"^[a-f0-9]{40,64}$", tree_oid):
            return MergeTreeResult(
                success=False, error=f"merge-tree returned invalid tree OID: {tree_oid!r}"
            )

        # Build a new commit whose tree is `tree_oid` with `base_ref` as parent.
        commit_tree = self._run(
            [
                "commit-tree",
                tree_oid,
                "-p",
                base_ref,
                "-m",
                f"speculative merge: {feature_branch} onto {base_ref}",
            ]
        )
        if commit_tree.returncode != 0:
            return MergeTreeResult(
                success=False,
                error=(commit_tree.stderr or "git commit-tree failed").strip(),
            )
        commit_sha = commit_tree.stdout.strip()

        # Point ref_name at the new commit atomically.
        update_ref = self._run(["update-ref", ref_name, commit_sha])
        if update_ref.returncode != 0:
            return MergeTreeResult(
                success=False,
                error=(update_ref.stderr or "git update-ref failed").strip(),
            )

        return MergeTreeResult(
            success=True,
            tree_oid=tree_oid,
            commit_sha=commit_sha,
        )

    def delete_speculative_refs(self, train_id: str) -> int:
        """Delete all refs under `refs/speculative/train-<train_id>/`."""
        if not re.match(r"^[a-f0-9]{8,32}$", train_id):
            raise InvalidRefNameError(f"train_id must be hex 8..32 chars: {train_id!r}")
        self._ensure_git_version()

        prefix = f"refs/speculative/train-{train_id}/"
        result = self._run(["for-each-ref", "--format=%(refname)", prefix])
        if result.returncode != 0:
            return 0
        refs = [r for r in result.stdout.splitlines() if r.strip()]
        deleted = 0
        for ref in refs:
            # Each ref from `for-each-ref` is already validated by git's ref parser,
            # but run it through our validator anyway for defense-in-depth.
            try:
                validate_speculative_ref_name(ref)
            except InvalidRefNameError:
                logger.warning("skipping unexpected ref during cleanup: %s", ref)
                continue
            delete = self._run(["update-ref", "-d", ref])
            if delete.returncode == 0:
                deleted += 1
        return deleted

    def fast_forward_main(self, speculative_ref: str) -> FastForwardResult:
        """Fast-forward main to `speculative_ref`."""
        validate_speculative_ref_name(speculative_ref)
        self._ensure_git_version()

        # Check that speculative_ref is a descendant of main (fast-forward safe).
        ancestor = self._run(["merge-base", "--is-ancestor", "main", speculative_ref])
        if ancestor.returncode != 0:
            return FastForwardResult(
                success=False,
                error="speculative_ref is not a descendant of main (non-fast-forward)",
            )

        # Get the SHA the speculative ref points to.
        rev = self._run(["rev-parse", speculative_ref])
        if rev.returncode != 0:
            return FastForwardResult(
                success=False,
                error=(rev.stderr or "git rev-parse failed").strip(),
            )
        new_sha = rev.stdout.strip()

        update = self._run(["update-ref", "refs/heads/main", new_sha])
        if update.returncode != 0:
            return FastForwardResult(
                success=False,
                error=(update.stderr or "git update-ref failed").strip(),
            )
        return FastForwardResult(success=True, new_main_sha=new_sha)

    def get_changed_files(self, base_ref: str, feature_branch: str) -> ChangedFiles:
        """Return files changed between base_ref and feature_branch."""
        if not (
            SPECULATIVE_REF_PATTERN.match(base_ref) or BRANCH_NAME_PATTERN.match(base_ref)
        ):
            raise InvalidRefNameError(f"base_ref invalid: {base_ref!r}")
        if not (
            SPECULATIVE_REF_PATTERN.match(feature_branch)
            or BRANCH_NAME_PATTERN.match(feature_branch)
        ):
            raise InvalidRefNameError(f"feature_branch invalid: {feature_branch!r}")
        self._ensure_git_version()

        result = self._run(["diff", "--name-status", f"{base_ref}...{feature_branch}"])
        if result.returncode != 0:
            return ChangedFiles()

        changed: list[str] = []
        added: list[str] = []
        deleted: list[str] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            status, path = parts[0].strip(), parts[1].strip()
            changed.append(path)
            if status.startswith("A"):
                added.append(path)
            elif status.startswith("D"):
                deleted.append(path)
        return ChangedFiles(changed_files=changed, added_files=added, deleted_files=deleted)

    def list_speculative_refs(self) -> list[str]:
        """Enumerate all refs under `refs/speculative/` (for crash recovery)."""
        self._ensure_git_version()
        result = self._run(["for-each-ref", "--format=%(refname)", "refs/speculative/"])
        if result.returncode != 0:
            return []
        return [r for r in result.stdout.splitlines() if r.strip()]


# ---------------------------------------------------------------------------
# Helper: parse conflict file list from merge-tree output
# ---------------------------------------------------------------------------


_CONFLICT_MARKER_PATTERNS = (
    re.compile(r"^CONFLICT \((?P<kind>[^)]+)\):.*?in (?P<path>.+?)$", re.MULTILINE),
    re.compile(r"^Auto-merging (?P<path>.+?)$", re.MULTILINE),
)


def _parse_conflict_files(stdout: str, stderr: str) -> list[str]:
    """Extract conflicting file paths from merge-tree --messages output.

    `git merge-tree --messages` prints "CONFLICT (content): Merge conflict in
    <path>" for content conflicts. We also watch stderr as a belt-and-braces
    check.
    """
    files: set[str] = set()
    for text in (stdout, stderr):
        if not text:
            continue
        for match in _CONFLICT_MARKER_PATTERNS[0].finditer(text):
            files.add(match.group("path").strip())
    return sorted(files)
