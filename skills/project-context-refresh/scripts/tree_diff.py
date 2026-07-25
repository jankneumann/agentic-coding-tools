"""Byte-level directory diff for tempdir-rendered producers.

Directory-scoped producers (decisions, OpenSpec projection) render their full
output set into a temporary directory and compare it to the committed tree. This
module owns that comparison and the generate-mode sync, so ``check`` is provably
write-free (it only ever reads the committed tree) and ``generate`` writes the
minimum set of changes.

Everything here is content-based: added/modified/deleted are decided by comparing
bytes, never modification times.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from _runtime import ChangeKind, RepositoryArtifact, sha256_hex


def _relative_files(root: Path, patterns: Iterable[str]) -> set[str]:
    found: set[str] = set()
    if not root.is_dir():
        return found
    for pattern in patterns:
        for path in root.rglob(pattern):
            if path.is_file():
                found.add(path.relative_to(root).as_posix())
    return found


def diff_trees(
    committed_root: Path,
    rendered_root: Path,
    *,
    path_prefix: str,
    patterns: Iterable[str] = ("*",),
) -> tuple[RepositoryArtifact, ...]:
    """Return the sorted artifacts describing how *rendered* differs from *committed*.

    ``path_prefix`` is the repository-relative directory both roots represent
    (e.g. ``docs/decisions``); artifact paths are ``<path_prefix>/<rel>``. Added
    and modified artifacts carry the rendered file's digest; deleted artifacts
    carry ``None``.
    """
    patterns = tuple(patterns)
    committed = _relative_files(committed_root, patterns)
    rendered = _relative_files(rendered_root, patterns)
    artifacts: list[RepositoryArtifact] = []

    for rel in rendered - committed:
        digest = sha256_hex((rendered_root / rel).read_bytes())
        artifacts.append(RepositoryArtifact(f"{path_prefix}/{rel}", ChangeKind.ADDED, digest))
    for rel in committed - rendered:
        artifacts.append(RepositoryArtifact(f"{path_prefix}/{rel}", ChangeKind.DELETED, None))
    for rel in rendered & committed:
        new_bytes = (rendered_root / rel).read_bytes()
        if new_bytes != (committed_root / rel).read_bytes():
            artifacts.append(
                RepositoryArtifact(
                    f"{path_prefix}/{rel}", ChangeKind.MODIFIED, sha256_hex(new_bytes)
                )
            )
    return tuple(sorted(artifacts, key=lambda a: (a.path, a.change.value)))


def sync_tree(
    committed_root: Path,
    rendered_root: Path,
    artifacts: Iterable[RepositoryArtifact],
    *,
    path_prefix: str,
) -> None:
    """Apply *artifacts* from *rendered_root* onto *committed_root* (generate mode).

    Only the diffed paths are written or removed, so an unchanged file is never
    rewritten (preserving byte-identical repeat generation).
    """
    prefix = f"{path_prefix}/"
    for artifact in artifacts:
        rel = artifact.path[len(prefix):] if artifact.path.startswith(prefix) else artifact.path
        dest = committed_root / rel
        if artifact.change is ChangeKind.DELETED:
            if dest.exists():
                dest.unlink()
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rendered_root / rel, dest)
