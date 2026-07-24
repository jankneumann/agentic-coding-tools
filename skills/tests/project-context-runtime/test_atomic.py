"""Atomic persistence and locking primitive tests.

Spec scenarios: project-context-refresh-records.5, .6, .12, .15
Design decisions: D3, D4
"""

from __future__ import annotations

import fcntl
import os
import threading
import time
from pathlib import Path

import atomic
import pytest


def test_canonical_bytes_are_stable_and_sorted() -> None:
    a = atomic.canonical_json_bytes({"b": 1, "a": [3, 2, 1]})
    b = atomic.canonical_json_bytes({"a": [3, 2, 1], "b": 1})
    assert a == b  # key order does not affect output
    assert a.endswith(b"\n")
    assert a.count(b"\n") >= 1
    # Sorted object keys.
    assert a.index(b'"a"') < a.index(b'"b"')


def test_atomic_write_reports_change_then_noop(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "record.json"
    changed, digest = atomic.atomic_write_json(target, {"x": 1})
    assert changed is True
    assert target.read_bytes() == atomic.canonical_json_bytes({"x": 1})
    # Rewriting identical logical content is a byte-observable no-op.
    changed2, digest2 = atomic.atomic_write_json(target, {"x": 1})
    assert changed2 is False
    assert digest2 == digest
    # A real change is reported.
    changed3, _ = atomic.atomic_write_json(target, {"x": 2})
    assert changed3 is True


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    atomic.atomic_write_json(target, {"x": 1})
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "record.json"]
    assert leftovers == []


def test_atomic_write_cleans_up_after_serialization_failure(tmp_path: Path) -> None:
    target = tmp_path / "record.json"

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        atomic.atomic_write_json(target, {"bad": Unserializable()})
    # No partial target and no stray temp file remain.
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_read_json_rejects_truncated_document(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    target.write_text('{"x": 1', encoding="utf-8")  # truncated
    import json

    with pytest.raises(json.JSONDecodeError):
        atomic.read_json(target)


def test_file_lock_provides_mutual_exclusion(tmp_path: Path) -> None:
    # flock locks attach to the open file description, so a second descriptor
    # (even in the same process) contends with a held exclusive lock.
    lock_path = tmp_path / "op.lock"
    holder_acquired = threading.Event()
    release_holder = threading.Event()

    def hold() -> None:
        with atomic.file_lock(lock_path):
            holder_acquired.set()
            release_holder.wait(timeout=5)

    holder = threading.Thread(target=hold)
    holder.start()
    try:
        assert holder_acquired.wait(timeout=5), "holder did not acquire lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
    finally:
        release_holder.set()
        holder.join(timeout=5)
    # After the holder releases, the lock is acquirable again.
    with atomic.file_lock(lock_path):
        pass


def test_file_lock_sequential_acquisition_does_not_block(tmp_path: Path) -> None:
    lock_path = tmp_path / "op.lock"
    start = time.monotonic()
    with atomic.file_lock(lock_path):
        pass
    with atomic.file_lock(lock_path):
        pass
    assert time.monotonic() - start < 5
