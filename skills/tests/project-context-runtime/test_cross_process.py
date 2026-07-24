"""End-to-end cross-process and cross-worktree runtime tests.

Spec scenarios: project-context-refresh-records.2, .4, .5, .6, .12, .15, .18
Contracts: all files under contracts/
Design decisions: D1, D2, D3, D4, D5
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import manifest as mf
import models as m
import pytest
import store

_SCRIPTS_DIR = Path(store.__file__).resolve().parent
REV = "1234abcd" * 5  # 40 hex chars
REPO_ID = "github.com/acme/repo"

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=_GIT_ENV)
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=_GIT_ENV)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, env=_GIT_ENV)
    return repo


def _run_child(repo: Path, code: str) -> str:
    env = {**os.environ, "PYTHONPATH": str(_SCRIPTS_DIR)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _load_facade() -> object:
    spec = importlib.util.spec_from_file_location(
        "pcr_facade", _SCRIPTS_DIR / "__init__.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_facade_exposes_supported_api_and_hides_atomic() -> None:
    facade = _load_facade()
    for name in (
        "OperationStore",
        "write_manifest",
        "project_manifest",
        "OperationRecord",
        "RefreshManifest",
        "ProducerResult",
        "derive_operation_id",
    ):
        assert hasattr(facade, name), name
    exported = set(facade.__all__)  # type: ignore[attr-defined]
    # Atomic persistence helpers stay private.
    assert "atomic_write_json" not in exported
    assert "file_lock" not in exported
    assert not hasattr(facade, "atomic_write_json")


def test_create_in_one_process_resume_in_another_then_manifest(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    created = s.create_or_load(REPO_ID, REV)
    op_id = created.operation_id

    # A separate process advances the operation to a terminal state.
    child = (
        "import store, models as m\n"
        f"s = store.OperationStore({str(git_repo)!r})\n"
        f"op = {op_id!r}\n"
        "s.begin_attempt(op)\n"
        "s.record_producer_result(op, m.ProducerResult("
        "'documentation','2.0.0', m.ProducerStatus.FRESH,"
        " artifacts=(m.RepositoryArtifact('docs/x.md', m.ChangeKind.ADDED, '1'*64),),"
        " validations=(m.ValidationResult('docs.lint', m.ValidationStatus.PASSED, 'ok'),)))\n"
        "r = s.finalize(op, m.OperationState.SUCCEEDED)\n"
        "print(r.state.value)\n"
    )
    assert _run_child(git_repo, child) == "succeeded"

    # The original process sees the terminal record with no singleton state.
    record = s.load(op_id)
    assert record.state is m.OperationState.SUCCEEDED
    assert record.producer_ids() == ("documentation",)


def test_linked_worktree_shares_operation_and_stages_manifest(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    created = s.create_or_load(REPO_ID, REV)
    op_id = created.operation_id
    s.begin_attempt(op_id)
    s.record_producer_result(
        op_id,
        m.ProducerResult(
            "documentation",
            "2.0.0",
            m.ProducerStatus.FRESH,
            artifacts=(m.RepositoryArtifact("docs/x.md", m.ChangeKind.ADDED, "1" * 64),),
        ),
    )
    s.finalize(op_id, m.OperationState.SUCCEEDED)

    # A managed worktree of the same clone must see the same operation.
    worktree = git_repo.parent / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(worktree), "HEAD"],
        cwd=git_repo,
        check=True,
        env=_GIT_ENV,
    )
    wt_store = store.OperationStore(worktree)
    assert wt_store.base_dir == s.base_dir  # shared git common dir
    shared = wt_store.load(op_id)
    assert shared.operation_id == op_id

    # A duplicate request from the worktree reuses the original identity.
    assert wt_store.create_or_load(REPO_ID, REV).operation_id == op_id

    # Emit the deterministic manifest staged inside the worktree.
    result = mf.write_manifest(shared, "openspec/context/refresh.json", repo_root=worktree)
    assert result.changed is True
    staged = worktree / "openspec" / "context" / "refresh.json"
    assert staged.exists()

    # Record the manifest pointer back on the shared operation.
    updated = wt_store.record_manifest(op_id, path=result.path, sha256=result.sha256)
    assert updated.manifest.status is m.ManifestPointerStatus.VALIDATED
    assert updated.manifest.sha256 == result.sha256

    # Re-emitting the same manifest is a no-op.
    assert mf.write_manifest(
        shared, "openspec/context/refresh.json", repo_root=worktree
    ).changed is False
