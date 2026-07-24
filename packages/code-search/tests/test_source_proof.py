from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from code_search_pkg.source_proof import (
    SourceProofError,
    normalize_repository_path,
    prove_source,
    validate_full_object_id,
    verify_source_unchanged,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path, *, object_format: str = "sha1") -> tuple[Path, str]:
    repo = tmp_path / f"repo-{object_format}"
    subprocess.run(
        ["git", "init", f"--object-format={object_format}", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Source Proof Test")
    (repo / "tracked.py").write_text("answer = 42\n", encoding="utf-8")
    _git(repo, "add", "tracked.py")
    _git(repo, "commit", "-m", "fixture")
    return repo, _git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize("length", [40, 64])
def test_validate_full_object_id_accepts_lowercase_full_hashes(length: int) -> None:
    revision = "a" * length

    assert validate_full_object_id(revision) == revision


@pytest.mark.parametrize(
    "revision",
    ["HEAD", "main", "abc1234", "A" * 40, "g" * 40, "a" * 41, "a" * 63],
)
def test_validate_full_object_id_rejects_symbolic_abbreviated_or_invalid(
    revision: str,
) -> None:
    with pytest.raises(SourceProofError) as caught:
        validate_full_object_id(revision)

    assert caught.value.code == "invalid_source_revision"


def test_prove_source_records_exact_clean_head_and_registered_git_evidence(
    tmp_path: Path,
) -> None:
    repo, revision = _init_repo(tmp_path)

    first = prove_source(repo, revision)
    repeated = prove_source(
        repo,
        revision,
        registered_repo_root=first.repo_root,
        registered_git_common_dir_fingerprint=first.git_common_dir_fingerprint,
    )

    assert first == repeated
    assert first.source_revision == revision
    assert first.repo_root == str(repo.resolve())
    assert len(first.git_common_dir_fingerprint) == 64
    assert len(first.evidence_fingerprint) == 64


def test_prove_source_supports_sha256_git_object_ids(tmp_path: Path) -> None:
    try:
        repo, revision = _init_repo(tmp_path, object_format="sha256")
    except subprocess.CalledProcessError:
        pytest.skip("installed Git does not support SHA-256 repositories")

    proof = prove_source(repo, revision)

    assert len(revision) == 64
    assert proof.source_revision == revision


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_prove_source_rejects_tracked_and_untracked_changes(
    tmp_path: Path,
    dirty_kind: str,
) -> None:
    repo, revision = _init_repo(tmp_path)
    target = repo / ("tracked.py" if dirty_kind == "tracked" else "untracked.py")
    target.write_text("changed = True\n", encoding="utf-8")

    with pytest.raises(SourceProofError) as caught:
        prove_source(repo, revision)

    assert caught.value.code == "source_dirty"
    assert "changed = True" not in str(caught.value)
    assert str(target) not in str(caught.value)


def test_prove_source_rejects_head_mismatch_without_exposing_git_output(
    tmp_path: Path,
) -> None:
    repo, revision = _init_repo(tmp_path)
    wrong_revision = ("0" if revision[0] != "0" else "1") + revision[1:]

    with pytest.raises(SourceProofError) as caught:
        prove_source(repo, wrong_revision)

    assert caught.value.code == "source_revision_mismatch"
    assert revision not in str(caught.value)


def test_prove_source_rejects_unregistered_root(tmp_path: Path) -> None:
    repo, revision = _init_repo(tmp_path)

    with pytest.raises(SourceProofError) as caught:
        prove_source(
            repo,
            revision,
            registered_repo_root=tmp_path / "some-other-root",
        )

    assert caught.value.code == "repository_identity_mismatch"


def test_prove_source_rejects_unregistered_git_common_directory(
    tmp_path: Path,
) -> None:
    repo, revision = _init_repo(tmp_path)

    with pytest.raises(SourceProofError) as caught:
        prove_source(
            repo,
            revision,
            registered_git_common_dir_fingerprint="0" * 64,
        )

    assert caught.value.code == "repository_identity_mismatch"


def test_verify_source_unchanged_rejects_mutation_before_readiness(
    tmp_path: Path,
) -> None:
    repo, revision = _init_repo(tmp_path)
    proof = prove_source(repo, revision)
    (repo / "appeared-later.py").write_text("late = True\n", encoding="utf-8")

    with pytest.raises(SourceProofError) as caught:
        verify_source_unchanged(proof)

    assert caught.value.code == "source_proof_lost"


def test_normalize_repository_path_returns_posix_relative_path(tmp_path: Path) -> None:
    repo, _ = _init_repo(tmp_path)
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)
    target = nested / "module.py"
    target.write_text("", encoding="utf-8")

    assert normalize_repository_path(repo, "src/./pkg/module.py") == "src/pkg/module.py"
    assert normalize_repository_path(repo, target) == "src/pkg/module.py"


def test_normalize_repository_path_rejects_parent_escape(tmp_path: Path) -> None:
    repo, _ = _init_repo(tmp_path)

    with pytest.raises(SourceProofError) as caught:
        normalize_repository_path(repo, "../outside.py")

    assert caught.value.code == "source_path_escape"


def test_normalize_repository_path_rejects_escaping_symlink(tmp_path: Path) -> None:
    repo, _ = _init_repo(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("private = True\n", encoding="utf-8")
    (repo / "link.py").symlink_to(outside)

    with pytest.raises(SourceProofError) as caught:
        normalize_repository_path(repo, "link.py")

    assert caught.value.code == "source_path_escape"
    assert "private = True" not in str(caught.value)


def test_normalize_repository_path_keeps_internal_symlink_manifest_path(
    tmp_path: Path,
) -> None:
    repo, _ = _init_repo(tmp_path)
    (repo / "target.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "link.py").symlink_to("target.py")

    assert normalize_repository_path(repo, "link.py") == "link.py"
