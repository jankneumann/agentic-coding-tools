"""Non-skipping contract proof for the fenced storage adapter boundary.

The deterministic fake models the frozen interface that ``storage_pg.StoragePublisher``
must implement. Live Postgres tests verify an implementation of the same contract, but
the required architectural behaviors do not depend on optional resources.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pytest


@dataclass(frozen=True, slots=True)
class Record:
    index_id: str
    storage_key: str
    attempt_count: int
    lease_token: str


@dataclass(frozen=True, slots=True)
class Attempt:
    index_id: str
    attempt_count: int


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    path: str
    value: str


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    content_hash: str
    chunk_count: int


@dataclass(frozen=True, slots=True)
class Verification:
    chunk_count: int
    file_count: int
    vector_index_present: bool


@runtime_checkable
class StoragePublisherContract(Protocol):
    async def prepare_attempt(
        self, record: Record, *, embedding_dim: int
    ) -> Attempt: ...

    async def copy_unchanged(
        self,
        parent_storage_key: str,
        attempt: Attempt,
        paths: Sequence[str],
    ) -> int: ...

    async def replace_file(
        self, attempt: Attempt, path: str, chunks: Sequence[Chunk]
    ) -> None: ...

    async def verify_attempt(
        self,
        attempt: Attempt,
        *,
        expected_chunks: int,
        expected_files: int,
    ) -> Verification: ...

    async def publish_attempt(self, record: Record, attempt: Attempt) -> None: ...

    async def cleanup_attempt(self, attempt: Attempt) -> None: ...


class LeaseFenceError(RuntimeError):
    pass


class AttemptVerificationError(RuntimeError):
    pass


class AtomicPublishError(RuntimeError):
    pass


class FakeStoragePublisher:
    """State-based reference model for copy-forward and fenced publication."""

    def __init__(self) -> None:
        self.attempt_rows: dict[Attempt, dict[str, tuple[Chunk, ...]]] = {}
        self.attempt_manifests: dict[Attempt, dict[str, ManifestEntry]] = {}
        self.published_rows: dict[str, dict[str, tuple[Chunk, ...]]] = {}
        self.published_manifests: dict[str, dict[str, ManifestEntry]] = {}
        self.current_fences: dict[str, tuple[str, int]] = {}
        self.fail_publish_after_rows = False

    def seed_published(
        self,
        record: Record,
        chunks: Iterable[Chunk],
        manifest: Iterable[ManifestEntry],
    ) -> None:
        self.published_rows[record.storage_key] = _rows_by_path(chunks)
        self.published_manifests[record.storage_key] = {
            entry.path: entry for entry in manifest
        }

    def seed_attempt_manifest(
        self, attempt: Attempt, entries: Iterable[ManifestEntry]
    ) -> None:
        """Model the attempt-manifest rows owned by the registry package."""
        self.attempt_manifests[attempt] = {entry.path: entry for entry in entries}

    def set_current_fence(self, record: Record) -> None:
        self.current_fences[record.index_id] = (
            record.lease_token,
            record.attempt_count,
        )

    async def prepare_attempt(self, record: Record, *, embedding_dim: int) -> Attempt:
        if embedding_dim <= 0:
            raise ValueError("embedding_dim must be positive")
        attempt = Attempt(record.index_id, record.attempt_count)
        # A retry always starts from a clean, generation-specific target.
        self.attempt_rows[attempt] = {}
        self.attempt_manifests[attempt] = {}
        return attempt

    async def copy_unchanged(
        self,
        parent_storage_key: str,
        attempt: Attempt,
        paths: Sequence[str],
    ) -> int:
        source_rows = self.published_rows[parent_storage_key]
        source_manifest = self.published_manifests[parent_storage_key]
        copied = 0
        for path in paths:
            if path not in source_manifest:
                raise AttemptVerificationError(
                    f"parent manifest does not prove unchanged path {path}"
                )
            self.attempt_rows[attempt][path] = source_rows[path]
            copied += len(source_rows[path])
        return copied

    async def replace_file(
        self, attempt: Attempt, path: str, chunks: Sequence[Chunk]
    ) -> None:
        if any(chunk.path != path for chunk in chunks):
            raise ValueError("all replacement chunks must belong to path")
        self.attempt_rows[attempt][path] = tuple(chunks)

    async def verify_attempt(
        self,
        attempt: Attempt,
        *,
        expected_chunks: int,
        expected_files: int,
    ) -> Verification:
        rows = self.attempt_rows[attempt]
        manifest = self.attempt_manifests[attempt]
        if set(rows) != set(manifest):
            raise AttemptVerificationError(
                "manifest coverage differs from target paths"
            )
        for path, entry in manifest.items():
            if len(rows[path]) != entry.chunk_count:
                raise AttemptVerificationError(
                    f"manifest chunk count differs for {path}"
                )
        if sum(len(chunks) for chunks in rows.values()) != expected_chunks:
            raise AttemptVerificationError("target chunk count differs")
        if len(rows) != expected_files:
            raise AttemptVerificationError("target file count differs")
        return Verification(
            chunk_count=expected_chunks,
            file_count=expected_files,
            vector_index_present=True,
        )

    async def publish_attempt(self, record: Record, attempt: Attempt) -> None:
        expected_fence = self.current_fences.get(record.index_id)
        supplied_fence = (record.lease_token, attempt.attempt_count)
        if expected_fence != supplied_fence or record.index_id != attempt.index_id:
            raise LeaseFenceError("attempt does not own the current publish fence")

        await self.verify_attempt(
            attempt,
            expected_chunks=sum(
                len(chunks) for chunks in self.attempt_rows[attempt].values()
            ),
            expected_files=len(self.attempt_rows[attempt]),
        )
        # Snapshot both artifacts before changing either published pointer. A real
        # adapter performs these assignments in one Postgres transaction.
        next_rows = dict(self.attempt_rows[attempt])
        next_manifest = dict(self.attempt_manifests[attempt])
        previous_rows = self.published_rows.get(record.storage_key)
        previous_manifest = self.published_manifests.get(record.storage_key)
        try:
            self.published_rows[record.storage_key] = next_rows
            if self.fail_publish_after_rows:
                raise AtomicPublishError("injected failure during atomic publication")
            self.published_manifests[record.storage_key] = next_manifest
        except Exception:
            if previous_rows is None:
                self.published_rows.pop(record.storage_key, None)
            else:
                self.published_rows[record.storage_key] = previous_rows
            if previous_manifest is None:
                self.published_manifests.pop(record.storage_key, None)
            else:
                self.published_manifests[record.storage_key] = previous_manifest
            raise

    async def cleanup_attempt(self, attempt: Attempt) -> None:
        self.attempt_rows.pop(attempt, None)
        self.attempt_manifests.pop(attempt, None)


def _rows_by_path(chunks: Iterable[Chunk]) -> dict[str, tuple[Chunk, ...]]:
    rows: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        rows.setdefault(chunk.path, []).append(chunk)
    return {path: tuple(path_chunks) for path, path_chunks in rows.items()}


@pytest.mark.asyncio
async def test_copy_forward_owns_only_manifest_proven_unchanged_rows() -> None:
    parent = Record("parent", "code_chunks__i_parent", 1, "lease-parent")
    record = Record("child", "code_chunks__i_child", 1, "lease-child")
    publisher = FakeStoragePublisher()
    publisher.seed_published(
        parent,
        [
            Chunk("a-1", "a.py", "old a"),
            Chunk("b-1", "b.py", "old b"),
            Chunk("deleted-1", "deleted.py", "deleted"),
        ],
        [
            ManifestEntry("a.py", "hash-a", 1),
            ManifestEntry("b.py", "hash-b", 1),
            ManifestEntry("deleted.py", "hash-deleted", 1),
        ],
    )
    publisher.set_current_fence(record)

    attempt = await publisher.prepare_attempt(record, embedding_dim=3)
    await publisher.copy_unchanged(parent.storage_key, attempt, ["a.py"])
    await publisher.replace_file(attempt, "b.py", [Chunk("b-2", "b.py", "new b")])
    publisher.seed_attempt_manifest(
        attempt,
        [
            ManifestEntry("a.py", "hash-a", 1),
            ManifestEntry("b.py", "hash-b2", 1),
        ],
    )
    await publisher.publish_attempt(record, attempt)

    assert set(publisher.published_rows[record.storage_key]) == {"a.py", "b.py"}
    assert publisher.published_rows[record.storage_key]["a.py"][0].value == "old a"
    assert publisher.published_rows[record.storage_key]["b.py"][0].value == "new b"
    assert "deleted.py" not in publisher.published_rows[record.storage_key]


@pytest.mark.asyncio
async def test_retry_starts_a_clean_generation_specific_attempt() -> None:
    first = Record("child", "code_chunks__i_child", 1, "lease-stale")
    retry = Record("child", "code_chunks__i_child", 2, "lease-current")
    publisher = FakeStoragePublisher()

    abandoned = await publisher.prepare_attempt(first, embedding_dim=3)
    await publisher.replace_file(
        abandoned, "partial.py", [Chunk("partial-1", "partial.py", "partial")]
    )
    replacement = await publisher.prepare_attempt(retry, embedding_dim=3)

    assert abandoned != replacement
    assert publisher.attempt_rows[abandoned] == {
        "partial.py": (Chunk("partial-1", "partial.py", "partial"),)
    }
    assert publisher.attempt_rows[replacement] == {}

    await publisher.cleanup_attempt(abandoned)
    assert abandoned not in publisher.attempt_rows
    assert replacement in publisher.attempt_rows


@pytest.mark.asyncio
async def test_stale_attempt_remains_isolated_after_replacement_publishes() -> None:
    stale_record = Record("child", "code_chunks__i_child", 1, "lease-stale")
    current_record = Record("child", "code_chunks__i_child", 2, "lease-current")
    publisher = FakeStoragePublisher()

    stale = await publisher.prepare_attempt(stale_record, embedding_dim=3)
    current = await publisher.prepare_attempt(current_record, embedding_dim=3)
    publisher.set_current_fence(current_record)
    await publisher.replace_file(
        current, "code.py", [Chunk("current-1", "code.py", "current")]
    )
    publisher.seed_attempt_manifest(
        current, [ManifestEntry("code.py", "hash-current", 1)]
    )
    await publisher.publish_attempt(current_record, current)

    await publisher.replace_file(
        stale, "code.py", [Chunk("stale-1", "code.py", "late stale write")]
    )
    publisher.seed_attempt_manifest(stale, [ManifestEntry("code.py", "hash-stale", 1)])
    with pytest.raises(LeaseFenceError, match="current publish fence"):
        await publisher.publish_attempt(stale_record, stale)

    assert publisher.published_rows[current_record.storage_key]["code.py"] == (
        Chunk("current-1", "code.py", "current"),
    )
    assert publisher.published_manifests[current_record.storage_key]["code.py"] == (
        ManifestEntry("code.py", "hash-current", 1)
    )


@pytest.mark.asyncio
async def test_failed_verification_leaves_existing_publish_atomically_unchanged() -> (
    None
):
    record = Record("child", "code_chunks__i_child", 2, "lease-current")
    publisher = FakeStoragePublisher()
    publisher.seed_published(
        record,
        [Chunk("ready-1", "ready.py", "ready")],
        [ManifestEntry("ready.py", "hash-ready", 1)],
    )
    publisher.set_current_fence(record)
    attempt = await publisher.prepare_attempt(record, embedding_dim=3)
    await publisher.replace_file(attempt, "new.py", [Chunk("new-1", "new.py", "new")])
    publisher.seed_attempt_manifest(
        attempt, [ManifestEntry("different.py", "hash-different", 1)]
    )

    with pytest.raises(AttemptVerificationError, match="manifest coverage"):
        await publisher.publish_attempt(record, attempt)

    assert publisher.published_rows[record.storage_key] == {
        "ready.py": (Chunk("ready-1", "ready.py", "ready"),)
    }
    assert publisher.published_manifests[record.storage_key] == {
        "ready.py": ManifestEntry("ready.py", "hash-ready", 1)
    }


@pytest.mark.asyncio
async def test_publish_reverifies_after_a_preliminary_check() -> None:
    record = Record("child", "code_chunks__i_child", 2, "lease-current")
    publisher = FakeStoragePublisher()
    publisher.set_current_fence(record)
    attempt = await publisher.prepare_attempt(record, embedding_dim=3)
    await publisher.replace_file(attempt, "new.py", [Chunk("new-1", "new.py", "new")])
    publisher.seed_attempt_manifest(attempt, [ManifestEntry("new.py", "hash-new", 1)])

    await publisher.verify_attempt(attempt, expected_chunks=1, expected_files=1)
    # Model a write in the gap after the preliminary check. Publication's
    # transaction-bound verification must observe and reject it.
    publisher.attempt_rows[attempt]["late.py"] = (Chunk("late-1", "late.py", "late"),)

    with pytest.raises(AttemptVerificationError, match="manifest coverage"):
        await publisher.publish_attempt(record, attempt)
    assert record.storage_key not in publisher.published_rows
    assert record.storage_key not in publisher.published_manifests


@pytest.mark.asyncio
async def test_publication_rolls_back_rows_and_manifest_as_one_atomic_unit() -> None:
    record = Record("child", "code_chunks__i_child", 2, "lease-current")
    publisher = FakeStoragePublisher()
    publisher.seed_published(
        record,
        [Chunk("ready-1", "ready.py", "ready")],
        [ManifestEntry("ready.py", "hash-ready", 1)],
    )
    publisher.set_current_fence(record)
    attempt = await publisher.prepare_attempt(record, embedding_dim=3)
    await publisher.replace_file(attempt, "new.py", [Chunk("new-1", "new.py", "new")])
    publisher.seed_attempt_manifest(attempt, [ManifestEntry("new.py", "hash-new", 1)])
    publisher.fail_publish_after_rows = True

    with pytest.raises(AtomicPublishError, match="injected failure"):
        await publisher.publish_attempt(record, attempt)

    assert publisher.published_rows[record.storage_key] == {
        "ready.py": (Chunk("ready-1", "ready.py", "ready"),)
    }
    assert publisher.published_manifests[record.storage_key] == {
        "ready.py": ManifestEntry("ready.py", "hash-ready", 1)
    }


def test_fake_structurally_implements_the_frozen_storage_publisher_interface() -> None:
    assert isinstance(FakeStoragePublisher(), StoragePublisherContract)
