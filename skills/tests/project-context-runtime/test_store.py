"""Durable operation-store tests.

Spec scenarios: project-context-refresh-records.1, .2, .3, .4, .5, .6, .7, .18
Contracts: context-refresh-operation.schema.json
Design decisions: D2, D3, D5
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import models as m
import pytest
import store

_SCRIPTS_DIR = Path(store.__file__).resolve().parent
REV_A = "a" * 40
REV_B = "b" * 40
REPO_ID = "github.com/acme/repo"


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, env=env)
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


# --- identity & idempotency ------------------------------------------------- #
def test_create_or_load_is_deterministic_and_idempotent(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    first = s.create_or_load(REPO_ID, REV_A)
    second = s.create_or_load(REPO_ID, REV_A)
    assert first.operation_id == second.operation_id
    assert first.created_at == second.created_at  # not recreated
    assert first.repository_id == REPO_ID and first.source_revision == REV_A
    # Exactly one record directory exists.
    op_dirs = list((s.base_dir).iterdir())
    assert [p.name for p in op_dirs] == [first.operation_id]


def test_distinct_revisions_are_isolated(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    a = s.create_or_load(REPO_ID, REV_A)
    b = s.create_or_load(REPO_ID, REV_B)
    assert a.operation_id != b.operation_id
    assert {p.name for p in s.base_dir.iterdir()} == {a.operation_id, b.operation_id}


def test_store_uses_git_common_dir(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    expected = (git_repo / ".git" / "project-context" / "refresh-operations").resolve()
    assert s.base_dir == expected
    assert s.base_dir.parent.parent.name == ".git"


# --- cross-process reload --------------------------------------------------- #
def test_later_process_resumes_record(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    created = s.create_or_load(REPO_ID, REV_A)
    s.begin_attempt(created.operation_id)
    out = _run_child(
        git_repo,
        "import store\n"
        f"s = store.OperationStore({str(git_repo)!r})\n"
        f"r = s.load({created.operation_id!r})\n"
        "print(r.state.value, r.attempt, r.record_revision)",
    )
    assert out == "running 1 2"


# --- concurrency ------------------------------------------------------------ #
def test_concurrent_creation_yields_one_record(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    results: list[str] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        results.append(s.create_or_load(REPO_ID, REV_A).operation_id)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(results)) == 1
    op_id = results[0]
    record = s.load(op_id)
    assert record.record_revision == 1  # only one creator wrote
    assert [p.name for p in s.base_dir.iterdir()] == [op_id]


# --- interrupted / malformed writes fail closed ----------------------------- #
def test_partial_record_fails_closed(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    record = s.create_or_load(REPO_ID, REV_A)
    record_path = s.base_dir / record.operation_id / "operation.json"
    record_path.write_text('{"schema_version": 1', encoding="utf-8")  # truncated
    with pytest.raises(m.CorruptRecordError):
        s.load(record.operation_id)


def test_tampered_identity_fails_closed(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    record = s.create_or_load(REPO_ID, REV_A)
    record_path = s.base_dir / record.operation_id / "operation.json"
    data = json.loads(record_path.read_text(encoding="utf-8"))
    data["repository_id"] = "github.com/evil/other"  # id no longer hashes to dir
    record_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(m.IdentityMismatchError):
        s.load(record.operation_id)


def test_unknown_version_on_disk_fails_closed(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    record = s.create_or_load(REPO_ID, REV_A)
    record_path = s.base_dir / record.operation_id / "operation.json"
    data = json.loads(record_path.read_text(encoding="utf-8"))
    data["schema_version"] = 99
    record_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(m.SchemaVersionError):
        s.load(record.operation_id)


# --- state machine ---------------------------------------------------------- #
def test_retry_follows_state_machine(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    op = s.create_or_load(REPO_ID, REV_A).operation_id

    running = s.begin_attempt(op)
    assert running.state is m.OperationState.RUNNING
    assert running.attempt == 1

    # Idempotent begin while running does not bump the attempt.
    again = s.begin_attempt(op)
    assert again.attempt == 1
    assert again.record_revision == running.record_revision

    failed = s.finalize(op, m.OperationState.FAILED, error=m.SafeError("Boom", "it broke"))
    assert failed.state is m.OperationState.FAILED
    assert failed.error is not None

    retried = s.begin_attempt(op)
    assert retried.state is m.OperationState.RUNNING
    assert retried.attempt == 2

    done = s.finalize(op, m.OperationState.SUCCEEDED)
    assert done.state is m.OperationState.SUCCEEDED
    assert done.error is None

    # succeeded is terminal.
    with pytest.raises(m.InvalidTransitionError):
        s.begin_attempt(op)


def test_finalize_failed_requires_error(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    op = s.create_or_load(REPO_ID, REV_A).operation_id
    s.begin_attempt(op)
    with pytest.raises(m.RecordValidationError):
        s.finalize(op, m.OperationState.FAILED)


def test_producer_result_requires_running(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    op = s.create_or_load(REPO_ID, REV_A).operation_id
    fresh = m.ProducerResult("documentation", "1", m.ProducerStatus.FRESH)
    with pytest.raises(m.InvalidTransitionError):
        s.record_producer_result(op, fresh)  # still pending


def test_duplicate_producer_result_rejected(git_repo: Path) -> None:
    s = store.OperationStore(git_repo)
    op = s.create_or_load(REPO_ID, REV_A).operation_id
    s.begin_attempt(op)
    fresh = m.ProducerResult("documentation", "1", m.ProducerStatus.FRESH)
    s.record_producer_result(op, fresh)
    with pytest.raises(m.DuplicateProducerError):
        s.record_producer_result(op, fresh)
