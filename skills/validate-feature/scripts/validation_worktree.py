#!/usr/bin/env python3
"""Run validation in a disposable worktree and persist only durable results.

The source checkout is never modified during validation except when the two
declared result artifacts are copied back immediately before teardown.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_SKILLS_ROOT = Path(__file__).resolve().parents[2]
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from shared.environment_profile import detect  # noqa: E402


logger = logging.getLogger(__name__)

PERSISTED_ARTIFACTS = ("validation-report.md", "validation-findings.json")


class EnvironmentProfile(Protocol):
    isolation_provided: bool
    source: str


class DirtyValidationSourceError(RuntimeError):
    """Raised when ephemeral validation would ignore source checkout changes."""


def _run_git(
    repo: Path,
    *args: str,
    input_bytes: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return result


def _git_text(repo: Path, *args: str) -> str:
    return _run_git(repo, *args).stdout.decode().strip()


def _is_dirty(repo: Path) -> bool:
    return bool(
        _run_git(
            repo,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ).stdout
    )


def _untracked_paths(repo: Path) -> list[Path]:
    output = _run_git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    ).stdout
    return [Path(raw.decode()) for raw in output.split(b"\0") if raw]


def _copy_untracked(source: Path, target: Path, paths: Sequence[Path]) -> None:
    for relative in paths:
        source_path = source / relative
        target_path = target / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            target_path.symlink_to(os.readlink(source_path))
        else:
            shutil.copy2(source_path, target_path)


def _capture_dirty_state(source: Path) -> tuple[bytes, bytes, list[Path]]:
    """Capture source state before the scratch path exists inside the repository."""
    return (
        _run_git(source, "diff", "--cached", "--binary", "HEAD").stdout,
        _run_git(source, "diff", "--binary").stdout,
        _untracked_paths(source),
    )


def _materialize_dirty_state(
    source: Path,
    scratch: Path,
    snapshot: tuple[bytes, bytes, list[Path]],
) -> str:
    """Reproduce staged, unstaged, and untracked state and return its tree id."""
    staged_patch, unstaged_patch, untracked = snapshot

    if staged_patch:
        _run_git(scratch, "apply", "--index", "--binary", input_bytes=staged_patch)
    if unstaged_patch:
        _run_git(scratch, "apply", "--binary", input_bytes=unstaged_patch)
    _copy_untracked(source, scratch, untracked)

    # The scratch index is disposable. Staging its complete materialized state
    # gives the report a stable Git tree id without touching the source index.
    _run_git(scratch, "add", "-A")
    return _git_text(scratch, "write-tree")


@dataclass
class ValidationWorktree:
    """Prepared validation location plus the identity of the validated tree."""

    source: Path
    path: Path
    change_id: str
    validated_commit: str
    validated_tree: str
    ephemeral: bool

    def record_identity(self) -> None:
        """Record the exact commit/materialized tree in durable artifacts."""
        change_dir = self.path / "openspec" / "changes" / self.change_id
        findings_path = change_dir / "validation-findings.json"
        if findings_path.is_file():
            try:
                findings = json.loads(findings_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("could not record validation identity in %s: %s", findings_path, exc)
            else:
                findings["validated_commit"] = self.validated_commit
                findings["validated_tree"] = self.validated_tree
                findings_path.write_text(json.dumps(findings, indent=2, sort_keys=True) + "\n")

        report_path = change_dir / "validation-report.md"
        if report_path.is_file():
            report = report_path.read_text()
            identities = (
                f"**Validated commit**: {self.validated_commit}\n"
                f"**Validated tree**: {self.validated_tree}\n"
            )
            report = re.sub(
                r"\*\*Validated commit\*\*:.*\n\*\*Validated tree\*\*:.*\n?",
                "",
                report,
            )
            report_path.write_text(identities + report)

    def persist_results(self) -> None:
        """Copy only the two declared durable validation artifacts to source."""
        if not self.ephemeral:
            return
        self.record_identity()
        source_change = self.path / "openspec" / "changes" / self.change_id
        target_change = self.source / "openspec" / "changes" / self.change_id
        for name in PERSISTED_ARTIFACTS:
            artifact = source_change / name
            if artifact.is_file():
                target_change.mkdir(parents=True, exist_ok=True)
                shutil.copy2(artifact, target_change / name)

    def teardown(self) -> None:
        """Remove the disposable checkout, including validation-only residue."""
        if not self.ephemeral:
            return
        result = _run_git(
            self.source,
            "worktree",
            "remove",
            "--force",
            str(self.path),
            check=False,
        )
        if result.returncode != 0 and self.path.exists():
            # This is an owned, uniquely named scratch directory. The force
            # fallback is intentionally limited to that exact resolved path.
            shutil.rmtree(self.path)
        _run_git(self.source, "worktree", "prune", check=False)


def _prepare(
    source: Path,
    change_id: str,
    *,
    include_dirty: bool,
    detector: Callable[[], EnvironmentProfile],
    scratch_root: Path | None,
) -> ValidationWorktree:
    source = Path(_git_text(source, "rev-parse", "--show-toplevel")).resolve()
    profile = detector()
    commit = _git_text(source, "rev-parse", "HEAD")

    if profile.isolation_provided:
        logger.warning(
            "--ephemeral downgraded to in-place validation: isolation is already provided by %s",
            profile.source,
        )
        tree = _git_text(source, "rev-parse", "HEAD^{tree}")
        return ValidationWorktree(source, source, change_id, commit, tree, False)

    dirty = _is_dirty(source)
    if dirty and not include_dirty:
        raise DirtyValidationSourceError(
            "--ephemeral refused a dirty source checkout because HEAD would be "
            "stale; pass --include-dirty to validate the exact index and working tree"
        )

    dirty_snapshot = _capture_dirty_state(source) if dirty else None
    root = (scratch_root or source / ".git-worktrees" / ".validation").resolve()
    root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f"{change_id}-", dir=root))
    scratch.rmdir()  # git worktree add requires the destination not to exist.
    try:
        _run_git(source, "worktree", "add", "--detach", str(scratch), commit)
        if dirty:
            assert dirty_snapshot is not None
            tree = _materialize_dirty_state(source, scratch, dirty_snapshot)
        else:
            tree = _git_text(scratch, "rev-parse", "HEAD^{tree}")
        return ValidationWorktree(source, scratch, change_id, commit, tree, True)
    except BaseException:
        if scratch.exists():
            _run_git(
                source,
                "worktree",
                "remove",
                "--force",
                str(scratch),
                check=False,
            )
        raise


@contextmanager
def validation_worktree(
    source: str | Path,
    change_id: str,
    *,
    include_dirty: bool = False,
    detector: Callable[[], EnvironmentProfile] = detect,
    scratch_root: str | Path | None = None,
) -> Iterator[ValidationWorktree]:
    """Yield an isolated validation checkout and always finalize it safely."""
    run = _prepare(
        Path(source),
        change_id,
        include_dirty=include_dirty,
        detector=detector,
        scratch_root=Path(scratch_root) if scratch_root is not None else None,
    )
    try:
        yield run
    finally:
        try:
            run.persist_results()
        finally:
            run.teardown()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--source", default=".")
    parser.add_argument("--include-dirty", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("a validation command is required after --")
    with validation_worktree(
        args.source,
        args.change_id,
        include_dirty=args.include_dirty,
    ) as run:
        logger.info(
            "validating commit=%s tree=%s path=%s",
            run.validated_commit,
            run.validated_tree,
            run.path,
        )
        command_env = {
            **os.environ,
            "VALIDATION_VALIDATED_COMMIT": run.validated_commit,
            "VALIDATION_VALIDATED_TREE": run.validated_tree,
        }
        return subprocess.run(
            command,
            cwd=run.path,
            env=command_env,
            check=False,
        ).returncode


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
