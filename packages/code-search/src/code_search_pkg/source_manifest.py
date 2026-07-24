"""Exact-revision tracked-file planning for incremental semantic indexing."""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from .indexing_policy import IndexingPolicy, evaluate_path
from .secret_scanner import SecretScanError, SecretScanStatus
from .source_proof import prove_source


_GIT_TIMEOUT_SECONDS = 30.0
_OBJECT_ID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REGULAR_MODES = frozenset({"100644", "100755"})
_SYMLINK_MODE = "120000"


class SourceManifestError(RuntimeError):
    """A sanitized fail-closed source-manifest planning error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SecretScanner(Protocol):
    def scan_bytes(self, content: bytes) -> object: ...


class ParentManifestEntry(Protocol):
    file_path: str
    git_blob_id: str | None
    git_entry_type: str | None
    eligible: bool
    content_digest: str | None
    chunk_digest: str | None
    chunk_count: int


@dataclass(frozen=True, slots=True)
class SourceFilePlan:
    """One tracked path's auditable eligibility and reuse decision."""

    path: str
    git_mode: str
    git_blob_id: str
    git_entry_type: str
    eligible: bool
    eligibility_reason: str
    content_digest: str | None
    disposition: str
    parent_chunk_digest: str | None = None
    parent_chunk_count: int | None = None


@dataclass(frozen=True, slots=True)
class SourceManifestPlan:
    """Complete current manifest plus storage actions relative to one parent."""

    source_revision: str
    files: tuple[SourceFilePlan, ...]
    changed_paths: tuple[str, ...]
    copied_paths: tuple[str, ...]
    removed_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TrackedEntry:
    path: str
    git_mode: str
    object_type: str
    object_id: str


def build_source_manifest(
    repo_root: str | Path,
    source_revision: str,
    policy: IndexingPolicy,
    scanner: SecretScanner,
    *,
    parent_manifest: Sequence[ParentManifestEntry] = (),
) -> SourceManifestPlan:
    """Plan exact tracked blobs, evaluating policy before any blob is opened."""

    proof = prove_source(repo_root, source_revision)
    root = Path(proof.repo_root)
    tracked = _list_tracked_entries(root, proof.source_revision)
    parents = _index_parent_manifest(parent_manifest)
    files: list[SourceFilePlan] = []
    changed: list[str] = []
    copied: list[str] = []

    for tracked_entry in tracked:
        decision = evaluate_path(root, tracked_entry.path, policy)
        entry_type = _entry_type(tracked_entry)
        if not decision.eligible:
            files.append(
                _excluded_plan(
                    tracked_entry,
                    entry_type,
                    decision.reason.value,
                )
            )
            continue
        if entry_type == "unsupported":
            files.append(
                _excluded_plan(
                    tracked_entry,
                    entry_type,
                    "unsupported_git_entry",
                )
            )
            continue
        if entry_type == "symlink":
            files.append(
                _excluded_plan(
                    tracked_entry,
                    entry_type,
                    "symlink_not_indexed",
                )
            )
            continue

        content = _read_blob(root, tracked_entry.object_id)
        _scan_or_fail(scanner, content)
        content_digest = hashlib.sha256(content).hexdigest()
        parent = parents.get(tracked_entry.path)
        if _can_copy(parent, tracked_entry, entry_type, content_digest):
            assert parent is not None
            copied.append(tracked_entry.path)
            files.append(
                SourceFilePlan(
                    path=tracked_entry.path,
                    git_mode=tracked_entry.git_mode,
                    git_blob_id=tracked_entry.object_id,
                    git_entry_type=entry_type,
                    eligible=True,
                    eligibility_reason="eligible",
                    content_digest=content_digest,
                    disposition="copied",
                    parent_chunk_digest=parent.chunk_digest,
                    parent_chunk_count=parent.chunk_count,
                )
            )
        else:
            changed.append(tracked_entry.path)
            files.append(
                SourceFilePlan(
                    path=tracked_entry.path,
                    git_mode=tracked_entry.git_mode,
                    git_blob_id=tracked_entry.object_id,
                    git_entry_type=entry_type,
                    eligible=True,
                    eligibility_reason="eligible",
                    content_digest=content_digest,
                    disposition="changed",
                )
            )

    current_by_path = {entry.path: entry for entry in files}
    removed = sorted(
        path
        for path, parent in parents.items()
        if parent.eligible
        and (path not in current_by_path or not current_by_path[path].eligible)
    )
    return SourceManifestPlan(
        source_revision=proof.source_revision,
        files=tuple(files),
        changed_paths=tuple(changed),
        copied_paths=tuple(copied),
        removed_paths=tuple(removed),
    )


def _excluded_plan(
    tracked: _TrackedEntry,
    entry_type: str,
    reason: str,
) -> SourceFilePlan:
    return SourceFilePlan(
        path=tracked.path,
        git_mode=tracked.git_mode,
        git_blob_id=tracked.object_id,
        git_entry_type=entry_type,
        eligible=False,
        eligibility_reason=reason,
        content_digest=None,
        disposition="excluded",
    )


def _list_tracked_entries(
    repo_root: Path, source_revision: str
) -> tuple[_TrackedEntry, ...]:
    output = _run_git_bytes(
        repo_root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        source_revision,
        "--",
    )
    entries: list[_TrackedEntry] = []
    seen: set[str] = set()
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            header, raw_path = record.split(b"\t", 1)
            raw_mode, raw_type, raw_object_id = header.split(b" ", 2)
            path = raw_path.decode("utf-8", errors="strict")
            mode = raw_mode.decode("ascii", errors="strict")
            object_type = raw_type.decode("ascii", errors="strict")
            object_id = raw_object_id.decode("ascii", errors="strict")
        except (UnicodeError, ValueError) as error:
            raise SourceManifestError(
                "invalid_git_tree",
                "Git tree contains an unsupported tracked entry",
            ) from error
        if not _is_lexical_repo_path(path) or not _OBJECT_ID_RE.fullmatch(object_id):
            raise SourceManifestError(
                "invalid_git_tree",
                "Git tree contains an unsupported tracked entry",
            )
        if path in seen:
            raise SourceManifestError(
                "invalid_git_tree",
                "Git tree contains duplicate tracked paths",
            )
        seen.add(path)
        entries.append(_TrackedEntry(path, mode, object_type, object_id))
    return tuple(sorted(entries, key=lambda entry: entry.path))


def _read_blob(repo_root: Path, blob_id: str) -> bytes:
    return _run_git_bytes(repo_root, "cat-file", "blob", blob_id)


def _run_git_bytes(repo_root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SourceManifestError(
            "git_manifest_failed",
            "Git source manifest could not be read",
        ) from error
    if result.returncode != 0:
        raise SourceManifestError(
            "git_manifest_failed",
            "Git source manifest could not be read",
        )
    return result.stdout


def _scan_or_fail(scanner: SecretScanner, content: bytes) -> None:
    try:
        result = scanner.scan_bytes(content)
    except SecretScanError as error:
        raise SourceManifestError(
            "secret_scan_failed",
            "local secret scan failed while planning source files",
        ) from error
    except Exception as error:
        raise SourceManifestError(
            "secret_scan_failed",
            "local secret scan failed while planning source files",
        ) from error
    if getattr(result, "status", None) is SecretScanStatus.FINDING:
        raise SourceManifestError(
            "secret_detected",
            "local secret scan rejected an eligible source file",
        )
    if getattr(result, "status", None) is not SecretScanStatus.CLEAN:
        raise SourceManifestError(
            "secret_scan_failed",
            "local secret scan returned an invalid result",
        )


def _index_parent_manifest(
    entries: Sequence[ParentManifestEntry],
) -> dict[str, ParentManifestEntry]:
    indexed: dict[str, ParentManifestEntry] = {}
    for entry in entries:
        path = entry.file_path
        if not _is_lexical_repo_path(path) or path in indexed:
            raise SourceManifestError(
                "invalid_parent_manifest",
                "published parent manifest is invalid",
            )
        indexed[path] = entry
    return indexed


def _can_copy(
    parent: ParentManifestEntry | None,
    current: _TrackedEntry,
    entry_type: str,
    content_digest: str,
) -> bool:
    return bool(
        parent is not None
        and parent.eligible
        and parent.git_blob_id == current.object_id
        and parent.git_entry_type == entry_type
        and parent.content_digest == content_digest
        and parent.chunk_digest is not None
        and _DIGEST_RE.fullmatch(parent.chunk_digest)
        and not isinstance(parent.chunk_count, bool)
        and parent.chunk_count >= 0
    )


def _entry_type(entry: _TrackedEntry) -> str:
    if entry.object_type == "blob" and entry.git_mode in _REGULAR_MODES:
        return "blob"
    if entry.object_type == "blob" and entry.git_mode == _SYMLINK_MODE:
        return "symlink"
    return "unsupported"


def _is_lexical_repo_path(path: str) -> bool:
    pure = PurePosixPath(path)
    return bool(
        path
        and "\0" not in path
        and "\\" not in path
        and not pure.is_absolute()
        and ".." not in pure.parts
        and pure.as_posix() == path
    )
