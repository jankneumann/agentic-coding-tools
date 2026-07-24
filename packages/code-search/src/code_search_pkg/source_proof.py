"""Lightweight proof that an index is reading one exact, immutable Git source."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_FULL_OBJECT_ID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_GIT_TIMEOUT_SECONDS = 10.0


class SourceProofError(RuntimeError):
    """A sanitized source-proof failure safe for operation results."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceProof:
    """Canonical evidence captured before indexing and checked before publish."""

    repo_root: str
    source_revision: str
    git_common_dir_fingerprint: str
    evidence_fingerprint: str


def validate_full_object_id(source_revision: str) -> str:
    """Reject ref names and abbreviated/malformed Git object IDs."""

    if not isinstance(source_revision, str) or not _FULL_OBJECT_ID.fullmatch(
        source_revision
    ):
        raise SourceProofError(
            "invalid_source_revision",
            "source revision must be a full lowercase Git object ID",
        )
    return source_revision


def normalize_repository_path(
    repo_root: str | Path,
    candidate: str | Path,
) -> str:
    """Return a canonical POSIX repository-relative path, following symlinks safely."""

    try:
        canonical_root = Path(repo_root).expanduser().resolve(strict=True)
        raw_candidate = Path(candidate)
        if not str(raw_candidate) or str(raw_candidate) == ".":
            raise ValueError("empty repository path")
        if not raw_candidate.is_absolute() and ".." in raw_candidate.parts:
            raise ValueError("parent traversal")
        joined = (
            raw_candidate
            if raw_candidate.is_absolute()
            else canonical_root / raw_candidate
        )
        lexical = Path(os.path.abspath(joined))
        lexical_relative = lexical.relative_to(canonical_root)
        resolved = joined.resolve(strict=False)
        resolved.relative_to(canonical_root)
        if not lexical_relative.parts:
            raise ValueError("repository root is not an indexable path")
        return lexical_relative.as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        raise SourceProofError(
            "source_path_escape",
            "candidate path is not contained in the proven repository",
        ) from error


def prove_source(
    repo_root: str | Path,
    source_revision: str,
    *,
    registered_repo_root: str | Path | None = None,
    registered_git_common_dir_fingerprint: str | None = None,
) -> SourceProof:
    """Prove canonical repository identity, exact HEAD, and a clean worktree."""

    validate_full_object_id(source_revision)
    try:
        requested_root = Path(repo_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise SourceProofError(
            "repository_unavailable",
            "repository root is unavailable",
        ) from error
    if not requested_root.is_dir():
        raise SourceProofError(
            "repository_unavailable",
            "repository root is unavailable",
        )

    git_root_output = _run_git(requested_root, "rev-parse", "--show-toplevel")
    try:
        git_root = Path(git_root_output).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise SourceProofError(
            "repository_identity_mismatch",
            "repository identity could not be proven",
        ) from error
    if git_root != requested_root:
        raise SourceProofError(
            "repository_identity_mismatch",
            "repository root does not match the Git worktree root",
        )

    if registered_repo_root is not None:
        try:
            registered_root = (
                Path(registered_repo_root).expanduser().resolve(strict=True)
            )
        except (OSError, RuntimeError) as error:
            raise SourceProofError(
                "repository_identity_mismatch",
                "registered repository identity is unavailable",
            ) from error
        if registered_root != requested_root:
            raise SourceProofError(
                "repository_identity_mismatch",
                "repository root does not match registered metadata",
            )

    common_output = _run_git(requested_root, "rev-parse", "--git-common-dir")
    common_path = Path(common_output)
    if not common_path.is_absolute():
        common_path = requested_root / common_path
    try:
        canonical_common_dir = common_path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise SourceProofError(
            "repository_identity_mismatch",
            "Git common-directory identity could not be proven",
        ) from error
    common_fingerprint = _sha256_text(str(canonical_common_dir))
    if (
        registered_git_common_dir_fingerprint is not None
        and registered_git_common_dir_fingerprint != common_fingerprint
    ):
        raise SourceProofError(
            "repository_identity_mismatch",
            "Git common-directory identity does not match registered metadata",
        )

    actual_head = _run_git(requested_root, "rev-parse", "--verify", "HEAD")
    if actual_head != source_revision:
        raise SourceProofError(
            "source_revision_mismatch",
            "worktree HEAD does not match the requested source revision",
        )

    status = _run_git(
        requested_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    if status:
        raise SourceProofError(
            "source_dirty",
            "worktree has tracked or untracked changes",
        )

    evidence = {
        "git_common_dir_fingerprint": common_fingerprint,
        "repo_root_fingerprint": _sha256_text(str(requested_root)),
        "source_revision": source_revision,
        "status": "clean",
        "version": 1,
    }
    return SourceProof(
        repo_root=str(requested_root),
        source_revision=source_revision,
        git_common_dir_fingerprint=common_fingerprint,
        evidence_fingerprint=_sha256_text(
            json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        ),
    )


def verify_source_unchanged(proof: SourceProof) -> SourceProof:
    """Repeat a proof immediately before readiness and fail with one safe code."""

    try:
        repeated = prove_source(
            proof.repo_root,
            proof.source_revision,
            registered_repo_root=proof.repo_root,
            registered_git_common_dir_fingerprint=proof.git_common_dir_fingerprint,
        )
    except SourceProofError as error:
        raise SourceProofError(
            "source_proof_lost",
            "source proof changed after indexing began",
        ) from error
    if repeated != proof:
        raise SourceProofError(
            "source_proof_lost",
            "source proof changed after indexing began",
        )
    return repeated


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SourceProofError(
            "source_proof_failed",
            "Git source proof could not be completed",
        ) from error
    if result.returncode != 0:
        raise SourceProofError(
            "source_proof_failed",
            "Git source proof could not be completed",
        )
    return result.stdout.strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
