#!/usr/bin/env python3
"""Run validation in a disposable worktree and persist only durable results.

The source checkout is never modified during validation except when the three
declared durable artifacts are copied back immediately before teardown.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import stat
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

PERSISTED_ARTIFACTS = (
    "architecture-impact.md",
    "validation-findings.json",
    "validation-report.md",
)
_CHANGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_OID_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


class EnvironmentProfile(Protocol):
    isolation_provided: bool
    source: str


class DirtyValidationSourceError(RuntimeError):
    """Raised when ephemeral validation would ignore source checkout changes."""


class UnsafeValidationPathError(RuntimeError):
    """Raised when a validation path escapes its declared ownership boundary."""


def _validate_change_id(change_id: str) -> None:
    if (
        not isinstance(change_id, str)
        or not _CHANGE_ID_PATTERN.fullmatch(change_id)
        or ".." in change_id
    ):
        raise ValueError(
            f"invalid change_id {change_id!r}: must match "
            f"{_CHANGE_ID_PATTERN.pattern!r} and must not contain '..'"
        )


def _require_contained(path: Path, parent: Path, label: str) -> Path:
    resolved_parent = parent.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_parent):
        raise UnsafeValidationPathError(
            f"unsafe {label}: {resolved} resolves outside {resolved_parent}"
        )
    return resolved


def _change_directory(repo: Path, change_id: str) -> Path:
    _validate_change_id(change_id)
    repo = repo.resolve()
    changes = _require_contained(repo / "openspec" / "changes", repo, "changes directory")
    candidate = (changes / change_id).resolve()
    if candidate.parent != changes:
        raise UnsafeValidationPathError(
            f"unsafe change directory: {candidate} is not a direct child of {changes}"
        )
    return candidate


def _artifact_path(change_dir: Path, name: str) -> Path:
    if name not in PERSISTED_ARTIFACTS:
        raise UnsafeValidationPathError(f"undeclared validation artifact: {name!r}")
    candidate = change_dir / name
    if candidate.is_symlink():
        raise UnsafeValidationPathError(f"refusing symlink artifact: {candidate}")
    resolved = candidate.resolve()
    if resolved.parent != change_dir.resolve():
        raise UnsafeValidationPathError(
            f"unsafe artifact path: {resolved} resolves outside {change_dir.resolve()}"
        )
    return candidate


def _read_regular_file(path: Path) -> bytes:
    """Read a regular file without following a final-component symlink."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise UnsafeValidationPathError(f"could not safely open artifact {path}: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise UnsafeValidationPathError(f"artifact is not a regular file: {path}")
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = -1
            return handle.read()
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)


def _atomic_write_bytes(target: Path, payload: bytes) -> None:
    """Atomically replace a regular destination without following symlinks."""
    if target.is_symlink():
        raise UnsafeValidationPathError(f"refusing symlink artifact: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.is_symlink():
            raise UnsafeValidationPathError(f"refusing symlink artifact: {target}")
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


def _run_git(
    repo: Path,
    *args: str,
    input_bytes: bytes | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_bytes,
        env=env,
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


def _materialized_tree_in_place(source: Path) -> str:
    """Write the current source content as a Git tree via a temporary index."""
    file_descriptor, index_name = tempfile.mkstemp(prefix="validation-index-")
    os.close(file_descriptor)
    index_path = Path(index_name)
    index_path.unlink()
    index_env = {**os.environ, "GIT_INDEX_FILE": str(index_path)}
    try:
        _run_git(source, "read-tree", "HEAD", env=index_env)
        _run_git(source, "add", "-A", env=index_env)
        return _run_git(source, "write-tree", env=index_env).stdout.decode().strip()
    finally:
        index_path.unlink(missing_ok=True)
        Path(f"{index_path}.lock").unlink(missing_ok=True)


def _artifact_baseline(source: Path, change_id: str) -> dict[str, bytes | None]:
    change_dir = _change_directory(source, change_id)
    baseline: dict[str, bytes | None] = {}
    for name in PERSISTED_ARTIFACTS:
        artifact = _artifact_path(change_dir, name)
        try:
            baseline[name] = _read_regular_file(artifact)
        except FileNotFoundError:
            baseline[name] = None
    return baseline


@dataclass
class ValidationWorktree:
    """Prepared validation location plus the identity of the validated tree."""

    source: Path
    path: Path
    change_id: str
    validated_commit: str
    validated_tree: str
    ephemeral: bool
    artifact_baseline: dict[str, bytes | None]
    scratch_root: Path | None = None

    def record_identity(self, changed_artifacts: set[str]) -> None:
        """Record the exact commit/materialized tree in durable artifacts."""
        change_dir = _change_directory(self.path, self.change_id)
        findings_path = _artifact_path(change_dir, "validation-findings.json")
        if "validation-findings.json" in changed_artifacts:
            try:
                findings = json.loads(_read_regular_file(findings_path))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("could not record validation identity in %s: %s", findings_path, exc)
            else:
                findings["validated_commit"] = self.validated_commit
                findings["validated_tree"] = self.validated_tree
                payload = (json.dumps(findings, indent=2, sort_keys=True) + "\n").encode()
                _atomic_write_bytes(findings_path, payload)

        report_path = _artifact_path(change_dir, "validation-report.md")
        if "validation-report.md" in changed_artifacts:
            report = _read_regular_file(report_path).decode()
            identities = (
                f"**Validated commit**: {self.validated_commit}\n"
                f"**Validated tree**: {self.validated_tree}\n"
            )
            report = re.sub(
                r"^\*\*Validated (?:commit|tree)\*\*:.*(?:\n|$)",
                "",
                report,
                flags=re.MULTILINE,
            )
            _atomic_write_bytes(report_path, (identities + report).encode())

    def persist_results(self) -> None:
        """Atomically copy only changed durable validation artifacts to source."""
        source_change = _change_directory(self.path, self.change_id)
        changed_artifacts: set[str] = set()
        for name in PERSISTED_ARTIFACTS:
            artifact = _artifact_path(source_change, name)
            try:
                payload = _read_regular_file(artifact)
            except FileNotFoundError:
                continue
            if payload != self.artifact_baseline[name]:
                changed_artifacts.add(name)
        self.record_identity(changed_artifacts)
        if not self.ephemeral:
            return
        target_change = _change_directory(self.source, self.change_id)
        for name in sorted(changed_artifacts):
            source_artifact = _artifact_path(source_change, name)
            target_artifact = _artifact_path(target_change, name)
            payload = _read_regular_file(source_artifact)
            _atomic_write_bytes(target_artifact, payload)

    def _assert_owned_scratch(self) -> None:
        if not self.ephemeral:
            return
        if self.scratch_root is None:
            raise UnsafeValidationPathError("ephemeral validation state has no scratch root")
        root = _require_contained(self.scratch_root, self.source, "scratch root")
        if self.path.is_symlink():
            raise UnsafeValidationPathError(f"refusing symlink scratch path: {self.path}")
        path = self.path.resolve()
        if path == self.source.resolve() or path.parent != root:
            raise UnsafeValidationPathError(
                f"unsafe scratch path: {path} is not an owned child of {root}"
            )
        registrations = {
            Path(line.removeprefix("worktree ")).resolve()
            for line in _git_text(self.source, "worktree", "list", "--porcelain").splitlines()
            if line.startswith("worktree ")
        }
        if path not in registrations:
            raise UnsafeValidationPathError(
                f"scratch path is not a registered Git worktree: {path}"
            )

    def teardown(self) -> None:
        """Remove the disposable checkout, including validation-only residue."""
        if not self.ephemeral:
            return
        self._assert_owned_scratch()
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
    _validate_change_id(change_id)
    source = Path(_git_text(source, "rev-parse", "--show-toplevel")).resolve()
    _change_directory(source, change_id)
    commit = _git_text(source, "rev-parse", "HEAD")
    dirty = _is_dirty(source)
    if dirty and not include_dirty:
        raise DirtyValidationSourceError(
            "--ephemeral refused a dirty source checkout because HEAD would be "
            "stale; pass --include-dirty to validate the exact index and working tree"
        )

    baseline = _artifact_baseline(source, change_id)
    profile = detector()

    if profile.isolation_provided:
        logger.warning(
            "--ephemeral downgraded to in-place validation: isolation is already provided by %s",
            profile.source,
        )
        tree = (
            _materialized_tree_in_place(source)
            if dirty
            else _git_text(source, "rev-parse", "HEAD^{tree}")
        )
        return ValidationWorktree(source, source, change_id, commit, tree, False, baseline)

    dirty_snapshot = _capture_dirty_state(source) if dirty else None
    root = (scratch_root or source / ".git-worktrees" / ".validation").resolve()
    _require_contained(root, source, "scratch root")
    root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f"{change_id}-", dir=root)).resolve()
    if scratch.parent != root:
        raise UnsafeValidationPathError(
            f"unsafe scratch path: {scratch} is not a direct child of {root}"
        )
    scratch.rmdir()  # git worktree add requires the destination not to exist.
    try:
        _run_git(source, "worktree", "add", "--detach", str(scratch), commit)
        if dirty:
            assert dirty_snapshot is not None
            tree = _materialize_dirty_state(source, scratch, dirty_snapshot)
        else:
            tree = _git_text(scratch, "rev-parse", "HEAD^{tree}")
        return ValidationWorktree(
            source,
            scratch,
            change_id,
            commit,
            tree,
            True,
            baseline,
            root,
        )
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


def _state_payload(run: ValidationWorktree) -> dict[str, object]:
    return {
        "artifact_baseline": {
            name: base64.b64encode(payload).decode() if payload is not None else None
            for name, payload in run.artifact_baseline.items()
        },
        "change_id": run.change_id,
        "ephemeral": run.ephemeral,
        "path": str(run.path),
        "scratch_root": str(run.scratch_root) if run.scratch_root else None,
        "source": str(run.source),
        "validated_commit": run.validated_commit,
        "validated_tree": run.validated_tree,
    }


def _public_state(run: ValidationWorktree) -> dict[str, object]:
    payload = _state_payload(run)
    payload.pop("artifact_baseline")
    return payload


def _write_state(path: Path, run: ValidationWorktree) -> None:
    if path.is_symlink():
        raise UnsafeValidationPathError(f"refusing symlink state file: {path}")
    payload = (json.dumps(_state_payload(run), indent=2, sort_keys=True) + "\n").encode()
    _atomic_write_bytes(path, payload)


def _load_state(path: Path) -> ValidationWorktree:
    if path.is_symlink():
        raise UnsafeValidationPathError(f"refusing symlink state file: {path}")
    try:
        raw = json.loads(_read_regular_file(path))
    except (FileNotFoundError, json.JSONDecodeError, TypeError) as exc:
        raise UnsafeValidationPathError(f"invalid validation state file {path}: {exc}") from exc
    try:
        change_id = raw["change_id"]
        _validate_change_id(change_id)
        source = Path(raw["source"]).resolve()
        canonical_source = Path(_git_text(source, "rev-parse", "--show-toplevel")).resolve()
        if source != canonical_source:
            raise UnsafeValidationPathError(
                f"validation state source {source} is not Git root {canonical_source}"
            )
        _change_directory(source, change_id)
        ephemeral = raw["ephemeral"]
        if not isinstance(ephemeral, bool):
            raise TypeError("ephemeral must be a boolean")
        scratch_root = Path(raw["scratch_root"]).resolve() if raw["scratch_root"] else None
        raw_path = Path(raw["path"])
        if raw_path.is_symlink():
            raise UnsafeValidationPathError(f"refusing symlink scratch path: {raw_path}")
        path_value = raw_path.resolve()
        baseline_raw = raw["artifact_baseline"]
        if set(baseline_raw) != set(PERSISTED_ARTIFACTS):
            raise ValueError("artifact baseline does not match durable allowlist")
        baseline = {
            name: base64.b64decode(value, validate=True) if value is not None else None
            for name, value in baseline_raw.items()
        }
        validated_commit = str(raw["validated_commit"])
        validated_tree = str(raw["validated_tree"])
        if not _OID_PATTERN.fullmatch(validated_commit) or not _OID_PATTERN.fullmatch(
            validated_tree
        ):
            raise ValueError("validated commit/tree is not a Git object id")
        run = ValidationWorktree(
            source=source,
            path=path_value,
            change_id=change_id,
            validated_commit=validated_commit,
            validated_tree=validated_tree,
            ephemeral=ephemeral,
            artifact_baseline=baseline,
            scratch_root=scratch_root,
        )
        if ephemeral:
            run._assert_owned_scratch()
        elif path_value != source or scratch_root is not None:
            raise UnsafeValidationPathError("invalid in-place validation state paths")
        return run
    except (KeyError, TypeError, ValueError) as exc:
        raise UnsafeValidationPathError(f"invalid validation state file {path}: {exc}") from exc


def _build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--source", default=".")
    parser.add_argument("--include-dirty", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _build_prepare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare an ephemeral validation checkout")
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--source", default=".")
    parser.add_argument("--include-dirty", action="store_true")
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--shell", action="store_true")
    return parser


def _build_finalize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persist and remove a validation checkout")
    parser.add_argument("--state-file", required=True)
    return parser


def _prepare_command(arguments: Sequence[str]) -> int:
    args = _build_prepare_parser().parse_args(arguments)
    run = _prepare(
        Path(args.source),
        args.change_id,
        include_dirty=args.include_dirty,
        detector=detect,
        scratch_root=None,
    )
    state_path = Path(args.state_file).resolve()
    try:
        _write_state(state_path, run)
    except BaseException:
        run.teardown()
        raise
    public = _public_state(run)
    if args.shell:
        variables = {
            "VALIDATION_SOURCE": public["source"],
            "VALIDATION_PATH": public["path"],
            "VALIDATION_STATE_FILE": str(state_path),
            "VALIDATION_VALIDATED_COMMIT": public["validated_commit"],
            "VALIDATION_VALIDATED_TREE": public["validated_tree"],
        }
        for name, value in variables.items():
            print(f"{name}={shlex.quote(str(value))}; export {name}")
    else:
        print(json.dumps(public, sort_keys=True))
    return 0


def _finalize_command(arguments: Sequence[str]) -> int:
    args = _build_finalize_parser().parse_args(arguments)
    state_path = Path(args.state_file).resolve()
    run = _load_state(state_path)
    try:
        run.persist_results()
    finally:
        try:
            run.teardown()
        finally:
            state_path.unlink(missing_ok=True)
    return 0


def _run_command(arguments: Sequence[str]) -> int:
    args = _build_run_parser().parse_args(arguments)
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


def main(arguments: Sequence[str] | None = None) -> int:
    argv = list(arguments if arguments is not None else sys.argv[1:])
    if argv[:1] == ["prepare"]:
        return _prepare_command(argv[1:])
    if argv[:1] == ["finalize"]:
        return _finalize_command(argv[1:])
    return _run_command(argv)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
