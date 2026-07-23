from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from code_search_pkg.registry import (
    FileManifestEntry,
    IndexIdentity,
    IndexLeaseConflictError,
    IndexNotFoundError,
    NamespaceKind,
    PUBLISH_ATTEMPT_MANIFEST_SQL,
    SemanticIndexRegistry,
)
from code_search_pkg.registry_models import LEGACY_FINGERPRINT


NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)
POLICY = "1" * 64
PIPELINE = "2" * 64
EMBEDDER = "3" * 64


def identity(
    *,
    revision: str = "a" * 40,
    policy: str = POLICY,
) -> IndexIdentity:
    return IndexIdentity(
        "repo",
        NamespaceKind.MAIN,
        "main",
        revision,
        "model",
        768,
        policy,
        PIPELINE,
        EMBEDDER,
    )


class IncrementalRegistryPool:
    def __init__(self) -> None:
        self.repositories: dict[str, UUID | None] = {"repo": None}
        self.indexes: dict[UUID, dict[str, Any]] = {}
        self.manifests: dict[tuple[UUID, int], list[dict[str, Any]]] = {}
        self.published: dict[UUID, list[dict[str, Any]]] = {}
        self.next_id = UUID("00000000-0000-4000-8000-000000000001")

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        if "/* registry:ensure */" in query:
            natural_key = args[2:11]
            for row in self.indexes.values():
                if (
                    tuple(
                        row[field]
                        for field in (
                            "repo_slug",
                            "namespace_kind",
                            "namespace_key",
                            "source_revision",
                            "embedder_model",
                            "embedding_dim",
                            "policy_fingerprint",
                            "pipeline_fingerprint",
                            "embedder_fingerprint",
                        )
                    )
                    == natural_key
                ):
                    return dict(row)
            row = {
                "index_id": args[0],
                "storage_key": args[1],
                "repo_slug": args[2],
                "namespace_kind": args[3],
                "namespace_key": args[4],
                "source_revision": args[5],
                "embedder_model": args[6],
                "embedding_dim": args[7],
                "policy_fingerprint": args[8],
                "pipeline_fingerprint": args[9],
                "embedder_fingerprint": args[10],
                "parent_index_id": None,
                "status": "pending",
                "attempt_count": 0,
                "chunk_count": None,
                "last_error": None,
                "lease_token": None,
                "lease_owner": None,
                "lease_expires_at": None,
                "retention_until": args[11],
                "started_at": None,
                "completed_at": None,
                "deleted_at": None,
                "created_at": args[12],
                "updated_at": args[12],
            }
            self.indexes[args[0]] = row
            return dict(row)
        if "/* registry:get */" in query:
            row = self.indexes.get(args[0])
            return None if row is None else dict(row)
        if "/* registry:find */" in query:
            for row in self.indexes.values():
                if (
                    tuple(
                        row[field]
                        for field in (
                            "repo_slug",
                            "namespace_kind",
                            "namespace_key",
                            "source_revision",
                            "embedder_model",
                            "embedding_dim",
                            "policy_fingerprint",
                            "pipeline_fingerprint",
                            "embedder_fingerprint",
                        )
                    )
                    == args
                ):
                    return dict(row)
            return None
        if "/* registry:get_canonical */" in query:
            if args[0] not in self.repositories:
                return None
            return {"canonical_index_id": self.repositories[args[0]]}
        if "/* registry:claim */" in query:
            row = self.indexes[args[0]]
            row.update(
                status="indexing",
                attempt_count=row["attempt_count"] + 1,
                lease_token=args[1],
                lease_owner=args[2],
                lease_expires_at=args[3],
                started_at=args[4],
                updated_at=args[4],
            )
            return dict(row)
        if "/* registry:renew */" in query:
            row = self.indexes[args[0]]
            if (
                row["status"] != "indexing"
                or row["lease_token"] != args[1]
                or row["lease_expires_at"] <= args[3]
            ):
                return None
            row.update(
                lease_expires_at=max(row["lease_expires_at"], args[2]),
                updated_at=args[3],
            )
            return dict(row)
        if "/* registry:set_parent */" in query:
            row = self.indexes[args[0]]
            if row["status"] != "indexing" or row["lease_token"] != args[1]:
                return None
            row.update(parent_index_id=args[2], updated_at=args[3])
            return dict(row)
        if "/* registry:replace_attempt_manifest */" in query:
            row = self.indexes[args[0]]
            current = (
                row["status"] == "indexing"
                and row["lease_token"] == args[1]
                and row["attempt_count"] == args[2]
                and row["lease_expires_at"] > args[4]
            )
            if current:
                import json

                self.manifests[(args[0], args[2])] = json.loads(args[3])
            return {"lease_valid": current}
        if "/* registry:publish_attempt_manifest */" in query:
            row = self.indexes[args[0]]
            current = (
                row["status"] == "indexing"
                and row["lease_token"] == args[1]
                and row["attempt_count"] == args[2]
                and row["lease_expires_at"] > args[3]
            )
            entries = self.manifests.get((args[0], args[2]), [])
            if current:
                self.published[args[0]] = [dict(entry) for entry in entries]
            return {"lease_valid": current, "entry_count": len(entries)}
        raise AssertionError(query)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if "/* registry:compatible_parents */" in query:
            matching = [
                dict(row)
                for row in self.indexes.values()
                if row["status"] == "ready"
                and tuple(
                    row[field]
                    for field in (
                        "repo_slug",
                        "namespace_kind",
                        "namespace_key",
                        "embedder_model",
                        "embedding_dim",
                        "policy_fingerprint",
                        "pipeline_fingerprint",
                        "embedder_fingerprint",
                    )
                )
                == args[:8]
                and all(
                    row[field] != LEGACY_FINGERPRINT
                    for field in (
                        "policy_fingerprint",
                        "pipeline_fingerprint",
                        "embedder_fingerprint",
                    )
                )
            ]
            return matching[: args[8]]
        if "/* registry:get_attempt_manifest */" in query:
            return [dict(entry) for entry in self.manifests.get((args[0], args[1]), ())]
        if "/* registry:get_published_manifest */" in query:
            return [dict(entry) for entry in self.published.get(args[0], ())]
        raise AssertionError(query)


def registry(pool: IncrementalRegistryPool) -> SemanticIndexRegistry:
    ids = iter(UUID(f"00000000-0000-4000-8000-{value:012x}") for value in range(1, 20))
    return SemanticIndexRegistry(
        pool, clock=lambda: NOW, uuid_factory=lambda: next(ids)
    )


def test_fingerprints_are_part_of_identity_and_v2_serialization() -> None:
    async def scenario() -> None:
        pool = IncrementalRegistryPool()
        repo = registry(pool)

        first = await repo.ensure_index(identity())
        changed_policy = await repo.ensure_index(identity(policy="4" * 64))

        assert first.index_id != changed_policy.index_id
        assert first.policy_fingerprint == POLICY
        assert first.to_dict()["parent_index_id"] is None
        assert first.to_dict()["embedder_fingerprint"] == EMBEDDER

    asyncio.run(scenario())


def test_exact_nonmutating_lookup_returns_ready_identity_or_none() -> None:
    async def scenario() -> None:
        pool = IncrementalRegistryPool()
        repo = registry(pool)
        created = await repo.ensure_index(identity())
        pool.indexes[created.index_id].update(
            status="ready",
            chunk_count=0,
            completed_at=NOW,
        )

        found = await repo.find_index(identity())
        missing = await repo.find_index(identity(policy="4" * 64))

        assert found is not None
        assert found.index_id == created.index_id
        assert found.status.value == "ready"
        assert missing is None

    asyncio.run(scenario())


def test_canonical_lookup_distinguishes_unset_from_missing_repository() -> None:
    async def scenario() -> None:
        pool = IncrementalRegistryPool()
        repo = registry(pool)

        assert await repo.get_canonical_index_id("repo") is None

        canonical = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
        pool.repositories["repo"] = canonical
        assert await repo.get_canonical_index_id("repo") == canonical

        with pytest.raises(IndexNotFoundError):
            await repo.get_canonical_index_id("missing")

    asyncio.run(scenario())


@pytest.mark.parametrize("fingerprint", ["", "a" * 63, "A" * 64, "g" * 64])
def test_identity_rejects_noncanonical_fingerprints(fingerprint: str) -> None:
    with pytest.raises(ValueError, match="fingerprint"):
        identity(policy=fingerprint)


def test_current_worker_can_renew_without_changing_attempt() -> None:
    async def scenario() -> None:
        pool = IncrementalRegistryPool()
        repo = registry(pool)
        pending = await repo.ensure_index(identity())
        claimed = await repo.claim_index(
            pending.index_id,
            lease_owner="worker",
            lease_duration=timedelta(seconds=30),
        )

        renewed = await repo.renew_index_lease(
            pending.index_id,
            claimed.lease_token,
            timedelta(minutes=5),
        )

        assert renewed.attempt_count == claimed.attempt_count
        assert renewed.lease_expires_at == NOW + timedelta(minutes=5)
        not_shortened = await repo.renew_index_lease(
            pending.index_id,
            claimed.lease_token,
            timedelta(seconds=5),
        )
        assert not_shortened.lease_expires_at == renewed.lease_expires_at

        pool.indexes[pending.index_id]["lease_token"] = UUID(
            "ffffffff-ffff-4fff-8fff-ffffffffffff"
        )
        with pytest.raises(IndexLeaseConflictError):
            await repo.renew_index_lease(
                pending.index_id,
                claimed.lease_token,
                timedelta(minutes=5),
            )

    asyncio.run(scenario())


def test_compatible_parent_lookup_excludes_legacy_and_links_under_current_lease() -> (
    None
):
    async def scenario() -> None:
        pool = IncrementalRegistryPool()
        repo = registry(pool)
        parent = await repo.ensure_index(identity(revision="a" * 40))
        parent_row = pool.indexes[parent.index_id]
        parent_row.update(
            status="ready",
            chunk_count=1,
            completed_at=NOW,
        )
        legacy_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
        pool.indexes[legacy_id] = {
            **parent_row,
            "index_id": legacy_id,
            "storage_key": "i_ffffffffffff4fff8fffffffffffffff",
            "source_revision": "b" * 40,
            "policy_fingerprint": LEGACY_FINGERPRINT,
            "pipeline_fingerprint": LEGACY_FINGERPRINT,
            "embedder_fingerprint": LEGACY_FINGERPRINT,
        }
        pool.indexes[legacy_id].update(
            status="ready",
            chunk_count=1,
            completed_at=NOW,
        )
        child = await repo.ensure_index(identity(revision="c" * 40))
        claimed = await repo.claim_index(
            child.index_id,
            lease_owner="worker",
            lease_duration=timedelta(minutes=5),
        )

        candidates = await repo.find_compatible_parents(identity(revision="c" * 40))
        linked = await repo.set_parent_index(
            child.index_id, claimed.lease_token, parent.index_id
        )

        assert [candidate.index_id for candidate in candidates] == [parent.index_id]
        assert linked.parent_index_id == parent.index_id

    asyncio.run(scenario())


def test_attempt_manifest_is_revision_scoped_and_current_attempt_fenced() -> None:
    async def scenario() -> None:
        pool = IncrementalRegistryPool()
        repo = registry(pool)
        pending = await repo.ensure_index(identity())
        claimed = await repo.claim_index(
            pending.index_id,
            lease_owner="worker",
            lease_duration=timedelta(minutes=5),
        )
        entries = (
            FileManifestEntry(
                file_path="src/app.py",
                git_blob_id="a" * 40,
                git_entry_type="blob",
                eligible=True,
                eligibility_reason="eligible",
                content_digest="b" * 64,
                chunk_digest="c" * 64,
                chunk_count=2,
            ),
            FileManifestEntry(
                file_path="build/output.js",
                git_blob_id=None,
                git_entry_type=None,
                eligible=False,
                eligibility_reason="generated",
                content_digest=None,
                chunk_digest=None,
                chunk_count=0,
            ),
        )

        stored = await repo.replace_attempt_manifest(
            pending.index_id,
            claimed.lease_token,
            claimed.attempt_count,
            entries,
        )

        expected = tuple(sorted(entries, key=lambda entry: entry.file_path))
        assert stored == expected
        assert (
            await repo.get_attempt_manifest(pending.index_id, claimed.attempt_count)
            == expected
        )
        with pytest.raises(IndexLeaseConflictError):
            await repo.replace_attempt_manifest(
                pending.index_id,
                claimed.lease_token,
                claimed.attempt_count + 1,
                entries,
            )

    asyncio.run(scenario())


def test_publish_manifest_is_composable_with_storage_transaction_and_fenced() -> None:
    async def scenario() -> None:
        pool = IncrementalRegistryPool()
        repo = registry(pool)
        pending = await repo.ensure_index(identity())
        claimed = await repo.claim_index(
            pending.index_id,
            lease_owner="worker",
            lease_duration=timedelta(minutes=5),
        )
        entry = FileManifestEntry(
            file_path="src/app.py",
            git_blob_id="a" * 40,
            git_entry_type="blob",
            eligible=True,
            eligibility_reason="eligible",
            content_digest="b" * 64,
            chunk_digest="c" * 64,
            chunk_count=2,
        )
        await repo.replace_attempt_manifest(
            pending.index_id,
            claimed.lease_token,
            claimed.attempt_count,
            (entry,),
        )
        published = await repo.publish_attempt_manifest(
            pending.index_id,
            claimed.lease_token,
            claimed.attempt_count,
            executor=pool,
        )
        assert "/* registry:publish_attempt_manifest */" in PUBLISH_ATTEMPT_MANIFEST_SQL
        assert published == 1
        assert await repo.get_published_manifest(pending.index_id) == (entry,)

    asyncio.run(scenario())


def test_manifest_rejects_unsafe_paths_and_incomplete_eligible_rows() -> None:
    with pytest.raises(ValueError, match="relative"):
        FileManifestEntry(
            file_path="../secret",
            git_blob_id=None,
            git_entry_type=None,
            eligible=False,
            eligibility_reason="denied",
            content_digest=None,
            chunk_digest=None,
            chunk_count=0,
        )
    with pytest.raises(ValueError, match="eligible"):
        FileManifestEntry(
            file_path="src/app.py",
            git_blob_id="a" * 40,
            git_entry_type="blob",
            eligible=True,
            eligibility_reason="eligible",
            content_digest=None,
            chunk_digest="c" * 64,
            chunk_count=1,
        )
