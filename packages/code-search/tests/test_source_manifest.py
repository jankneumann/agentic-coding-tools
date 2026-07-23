from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from code_search_pkg.indexing_policy import IndexingPolicy
from code_search_pkg.registry_models import FileManifestEntry
from code_search_pkg.secret_scanner import (
    SecretScanError,
    SecretScanResult,
    SecretScanStatus,
)
from code_search_pkg.source_manifest import (
    SourceManifestError,
    build_source_manifest,
)
from code_search_pkg.source_proof import SourceProofError


class RecordingScanner:
    def __init__(self) -> None:
        self.contents: list[bytes] = []

    def scan_bytes(self, content: bytes) -> SecretScanResult:
        self.contents.append(content)
        return SecretScanResult(SecretScanStatus.CLEAN, "clean")


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
    )
    return repo


def commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=True,
        capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def permissive_policy() -> IndexingPolicy:
    return IndexingPolicy(include=("**",), read_allow=("**",))


def test_manifest_enumerates_tracked_paths_nul_safely_and_reads_only_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_bytes(b"print('ok')\n")
    unusual = repo / "src" / "odd\tname.py"
    unusual.write_bytes(b"ODD = True\n")
    multiline = repo / "src" / "odd\nname.py"
    multiline.write_bytes(b"MULTILINE = True\n")
    denied = repo / "src" / "denied.py"
    denied.write_bytes(b"DO_NOT_READ = True\n")
    os.chmod(repo / "src" / "app.py", 0o755)
    revision = commit_all(repo, "initial")
    scanner = RecordingScanner()

    from code_search_pkg import source_manifest

    original_read_blob = source_manifest._read_blob
    read_blob_ids: list[str] = []

    def recording_read_blob(root: Path, blob_id: str) -> bytes:
        read_blob_ids.append(blob_id)
        return original_read_blob(root, blob_id)

    monkeypatch.setattr(source_manifest, "_read_blob", recording_read_blob)
    plan = build_source_manifest(
        repo,
        revision,
        IndexingPolicy(
            include=("src/**",),
            read_allow=("src/**",),
            deny=("src/denied.py",),
        ),
        scanner,
    )

    by_path = {entry.path: entry for entry in plan.files}
    assert tuple(by_path) == (
        "src/app.py",
        "src/denied.py",
        "src/odd\tname.py",
        "src/odd\nname.py",
    )
    assert by_path["src/app.py"].git_mode == "100755"
    assert by_path["src/app.py"].git_entry_type == "blob"
    assert by_path["src/denied.py"].eligible is False
    assert by_path["src/denied.py"].eligibility_reason == "denied"
    assert scanner.contents == [
        b"print('ok')\n",
        b"ODD = True\n",
        b"MULTILINE = True\n",
    ]
    assert len(read_blob_ids) == 3
    assert plan.changed_paths == (
        "src/app.py",
        "src/odd\tname.py",
        "src/odd\nname.py",
    )
    assert plan.copied_paths == ()
    assert plan.removed_paths == ()


def test_compatible_parent_copies_only_same_path_blob_type_content_and_chunk_set(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path)
    (repo / "src").mkdir()
    for name, content in (
        ("same.py", b"SAME = 1\n"),
        ("changed.py", b"VALUE = 1\n"),
        ("gone.py", b"GONE = 1\n"),
        ("old_name.py", b"RENAMED = 1\n"),
    ):
        (repo / "src" / name).write_bytes(content)
    first_revision = commit_all(repo, "first")
    first = build_source_manifest(
        repo, first_revision, permissive_policy(), RecordingScanner()
    )
    parent_manifest = tuple(
        FileManifestEntry(
            file_path=entry.path,
            git_blob_id=entry.git_blob_id,
            git_entry_type=entry.git_entry_type,
            eligible=True,
            eligibility_reason="eligible",
            content_digest=entry.content_digest,
            chunk_digest="d" * 64,
            chunk_count=1,
        )
        for entry in first.files
    )

    (repo / "src" / "changed.py").write_bytes(b"VALUE = 2\n")
    (repo / "src" / "gone.py").unlink()
    (repo / "src" / "old_name.py").rename(repo / "src" / "new_name.py")
    second_revision = commit_all(repo, "second")

    second = build_source_manifest(
        repo,
        second_revision,
        permissive_policy(),
        RecordingScanner(),
        parent_manifest=parent_manifest,
    )

    assert second.copied_paths == ("src/same.py",)
    assert second.changed_paths == ("src/changed.py", "src/new_name.py")
    assert second.removed_paths == ("src/gone.py", "src/old_name.py")
    same = next(entry for entry in second.files if entry.path == "src/same.py")
    assert same.parent_chunk_digest == "d" * 64
    assert same.parent_chunk_count == 1


def test_invalid_parent_chunk_digest_forces_changed_file(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "app.py").write_bytes(b"VALUE = 1\n")
    revision = commit_all(repo, "first")
    baseline = build_source_manifest(
        repo, revision, permissive_policy(), RecordingScanner()
    )
    current = baseline.files[0]
    invalid_parent = SimpleNamespace(
        file_path=current.path,
        git_blob_id=current.git_blob_id,
        git_entry_type=current.git_entry_type,
        eligible=True,
        content_digest=current.content_digest,
        chunk_digest="invalid",
        chunk_count=1,
    )

    plan = build_source_manifest(
        repo,
        revision,
        permissive_policy(),
        RecordingScanner(),
        parent_manifest=(invalid_parent,),
    )

    assert plan.changed_paths == ("app.py",)
    assert plan.copied_paths == ()


def test_newly_ineligible_parent_path_is_removed_without_source_read(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "private.py").write_bytes(b"PRIVATE = 1\n")
    revision = commit_all(repo, "first")
    baseline = build_source_manifest(
        repo, revision, permissive_policy(), RecordingScanner()
    )
    current = baseline.files[0]
    parent = FileManifestEntry(
        file_path=current.path,
        git_blob_id=current.git_blob_id,
        git_entry_type=current.git_entry_type,
        eligible=True,
        eligibility_reason="eligible",
        content_digest=current.content_digest,
        chunk_digest="d" * 64,
        chunk_count=1,
    )
    scanner = RecordingScanner()

    plan = build_source_manifest(
        repo,
        revision,
        IndexingPolicy(deny=("src/private.py",)),
        scanner,
        parent_manifest=(parent,),
    )

    entry = plan.files[0]
    assert entry.eligible is False
    assert entry.content_digest is None
    assert scanner.contents == []
    assert plan.removed_paths == ("src/private.py",)


def test_internal_symlink_is_audited_but_not_embedded_as_target_content(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path)
    (repo / "target.py").write_bytes(b"TARGET = 1\n")
    (repo / "link.py").symlink_to("target.py")
    revision = commit_all(repo, "symlink")
    scanner = RecordingScanner()

    plan = build_source_manifest(
        repo,
        revision,
        permissive_policy(),
        scanner,
    )

    by_path = {entry.path: entry for entry in plan.files}
    assert by_path["link.py"].git_entry_type == "symlink"
    assert by_path["link.py"].eligible is False
    assert by_path["link.py"].eligibility_reason == "symlink_not_indexed"
    assert plan.changed_paths == ("target.py",)
    assert scanner.contents == [b"TARGET = 1\n"]


@pytest.mark.parametrize("outcome", ["finding", "error", "unexpected"])
def test_scanner_findings_and_failures_abort_without_source_evidence(
    tmp_path: Path,
    outcome: str,
) -> None:
    repo = init_repo(tmp_path)
    (repo / "app.py").write_bytes(b"not persisted in errors")
    revision = commit_all(repo, "first")

    class FailingScanner:
        def scan_bytes(self, _content: bytes) -> SecretScanResult:
            if outcome == "finding":
                return SecretScanResult(
                    SecretScanStatus.FINDING,
                    "secret_detected",
                    "test_rule",
                )
            if outcome == "error":
                raise SecretScanError("scanner_timeout", "safe scanner failure")
            raise RuntimeError("raw source scanner detail")

    with pytest.raises(SourceManifestError) as caught:
        build_source_manifest(
            repo,
            revision,
            permissive_policy(),
            FailingScanner(),
        )

    assert caught.value.code in {"secret_detected", "secret_scan_failed"}
    assert "not persisted" not in str(caught.value)
    assert "raw source" not in str(caught.value)


def test_dirty_or_mismatched_worktree_is_rejected_before_enumeration(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path)
    (repo / "app.py").write_bytes(b"VALUE = 1\n")
    revision = commit_all(repo, "first")
    (repo / "app.py").write_bytes(b"DIRTY = 1\n")

    with pytest.raises(SourceProofError):
        build_source_manifest(
            repo,
            revision,
            permissive_policy(),
            RecordingScanner(),
        )
