from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from code_search_pkg.registry import (
    CanonicalPromotionError,
    GarbageCollectionResult,
    IndexIdentity,
    IndexLeaseConflictError,
    IndexNotFoundError,
    IndexStatus,
    NamespaceKind,
    SemanticIndexRegistry,
)
from fakes import FakeRegistryPool


NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)
SHA1 = "a" * 40
SHA2 = "b" * 40


def identity(
    *,
    repo: str = "repo",
    kind: NamespaceKind = NamespaceKind.MAIN,
    key: str = "main",
    revision: str = SHA1,
) -> IndexIdentity:
    return IndexIdentity(repo, kind, key, revision, "model", 768)


def registry(pool: FakeRegistryPool) -> SemanticIndexRegistry:
    next_uuid = iter(
        UUID(f"00000000-0000-4000-8000-{number:012x}") for number in range(1, 100)
    )
    return SemanticIndexRegistry(
        pool, clock=lambda: NOW, uuid_factory=lambda: next(next_uuid)
    )


def test_concurrent_ensure_returns_one_authoritative_record() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        repo = registry(pool)

        first, second = await asyncio.gather(
            repo.ensure_index(identity()), repo.ensure_index(identity())
        )

        assert first.index_id == second.index_id
        assert first.storage_key == second.storage_key
        assert len(pool.indexes) == 1

        feature = await repo.ensure_index(
            identity(kind=NamespaceKind.FEATURE, key="feature/one")
        )
        assert feature.index_id != first.index_id

    asyncio.run(scenario())


def test_ensure_missing_repository_returns_typed_not_found_without_fk_error() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        repo = registry(pool)

        with pytest.raises(IndexNotFoundError):
            await repo.ensure_index(identity(repo="missing"))

        assert pool.indexes == {}
        assert "FROM code_search_registry" in pool.executed_sql[-1]

    asyncio.run(scenario())


def test_missing_identity_is_distinct_from_an_illegal_claim_transition() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        repo = registry(pool)
        missing = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")

        with pytest.raises(IndexNotFoundError):
            await repo.claim_index(
                missing, lease_owner="worker", lease_duration=timedelta(minutes=1)
            )

        pending = await repo.ensure_index(identity())
        claimed = await repo.claim_index(
            pending.index_id, lease_owner="worker", lease_duration=timedelta(minutes=1)
        )
        with pytest.raises(IndexNotFoundError):
            await repo.mark_ready(missing, claimed.lease_token, chunk_count=1)

    asyncio.run(scenario())


def test_lease_guarded_ready_completion_rejects_stale_workers() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        repo = registry(pool)
        pending = await repo.ensure_index(identity())

        claimed = await repo.claim_index(
            pending.index_id,
            lease_owner="worker-1",
            lease_duration=timedelta(minutes=5),
        )
        ready = await repo.mark_ready(
            pending.index_id, claimed.lease_token, chunk_count=12
        )

        assert ready.status is IndexStatus.READY
        assert ready.chunk_count == 12
        assert ready.completed_at == NOW
        assert ready.lease_token is None
        with pytest.raises(IndexLeaseConflictError):
            await repo.mark_ready(pending.index_id, claimed.lease_token, chunk_count=13)

    asyncio.run(scenario())


def test_expired_lease_takeover_increments_attempt_and_rejects_old_token() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        current_time = NOW
        next_uuid = iter(
            [
                UUID("00000000-0000-4000-8000-000000000001"),
                UUID("00000000-0000-4000-8000-000000000002"),
                UUID("00000000-0000-4000-8000-000000000003"),
            ]
        )
        repo = SemanticIndexRegistry(
            pool, clock=lambda: current_time, uuid_factory=lambda: next(next_uuid)
        )
        pending = await repo.ensure_index(identity())
        first = await repo.claim_index(
            pending.index_id,
            lease_owner="worker-1",
            lease_duration=timedelta(seconds=5),
        )
        current_time = NOW + timedelta(seconds=6)
        second = await repo.claim_index(
            pending.index_id,
            lease_owner="worker-2",
            lease_duration=timedelta(minutes=1),
        )

        assert second.attempt_count == 2
        assert second.lease_token != first.lease_token
        with pytest.raises(IndexLeaseConflictError):
            await repo.mark_failed(pending.index_id, first.lease_token, "late failure")

    asyncio.run(scenario())


def test_failed_and_not_configured_outcomes_are_durable_and_retryable() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        repo = registry(pool)
        first = await repo.ensure_index(identity())
        claimed = await repo.claim_index(
            first.index_id, lease_owner="worker", lease_duration=timedelta(minutes=1)
        )
        failed = await repo.mark_failed(first.index_id, claimed.lease_token, "boom")
        retried = await repo.claim_index(
            first.index_id, lease_owner="worker", lease_duration=timedelta(minutes=1)
        )
        disabled = await repo.mark_not_configured(
            first.index_id, retried.lease_token, "disabled"
        )

        assert failed.status is IndexStatus.FAILED
        assert failed.last_error == "boom"
        assert disabled.status is IndexStatus.NOT_CONFIGURED
        assert disabled.last_error == "disabled"
        assert disabled.attempt_count == 2

    asyncio.run(scenario())


def test_canonical_promotion_requires_ready_same_repo_main_and_supports_cas() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        pool.add_repository("other")
        repo = registry(pool)
        main1 = await repo.ensure_index(identity())
        feature = await repo.ensure_index(
            identity(kind=NamespaceKind.FEATURE, key="feature/one")
        )
        main2 = await repo.ensure_index(identity(revision=SHA2))

        with pytest.raises(CanonicalPromotionError):
            await repo.promote_canonical("repo", main1.index_id)
        ready1 = await make_ready(repo, main1.index_id)
        ready_feature = await make_ready(repo, feature.index_id)
        ready2 = await make_ready(repo, main2.index_id)

        assert (
            await repo.promote_canonical(
                "repo", ready1.index_id, expected_current_index_id=None
            )
            == ready1.index_id
        )
        with pytest.raises(CanonicalPromotionError):
            await repo.promote_canonical(
                "repo", ready2.index_id, expected_current_index_id=None
            )
        assert pool.repositories["repo"] == ready1.index_id
        with pytest.raises(CanonicalPromotionError):
            await repo.promote_canonical("repo", ready_feature.index_id)
        with pytest.raises(CanonicalPromotionError):
            await repo.promote_canonical("other", ready2.index_id)
        assert pool.repositories["repo"] == ready1.index_id

        assert (
            await repo.promote_canonical(
                "repo",
                ready2.index_id,
                expected_current_index_id=ready1.index_id,
            )
            == ready2.index_id
        )

    asyncio.run(scenario())


def test_gc_is_storage_first_excludes_protected_rows_and_retries_failures() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        repo = registry(pool)
        expired = NOW - timedelta(days=1)
        main = await repo.ensure_index(identity(), retention_until=expired)
        deletable = await repo.ensure_index(
            identity(kind=NamespaceKind.FEATURE, key="feature/delete"),
            retention_until=expired,
        )
        failing = await repo.ensure_index(
            identity(kind=NamespaceKind.WORK_PACKAGE, key="wp-fail", revision=SHA2),
            retention_until=expired,
        )
        active = await repo.ensure_index(
            identity(kind=NamespaceKind.FEATURE, key="feature/active", revision=SHA2),
            retention_until=expired,
        )
        await repo.claim_index(
            active.index_id, lease_owner="worker", lease_duration=timedelta(minutes=5)
        )
        canonical = await make_ready(repo, main.index_id)
        await repo.promote_canonical("repo", canonical.index_id)
        calls: list[str] = []

        async def delete_storage(storage_key: str) -> None:
            calls.append(storage_key)
            if storage_key == failing.storage_key:
                raise RuntimeError("storage unavailable")
            assert (
                pool.indexes[deletable.index_id]["status"] == IndexStatus.DELETING.value
            )

        result = await repo.collect_garbage(delete_storage)

        assert result == GarbageCollectionResult(
            deleted=(deletable.index_id,), failed=(failing.index_id,)
        )
        assert calls == [deletable.storage_key, failing.storage_key]
        assert pool.indexes[main.index_id]["status"] == "ready"
        assert pool.indexes[active.index_id]["status"] == "indexing"
        assert pool.indexes[deletable.index_id]["status"] == "deleted"
        assert pool.indexes[failing.index_id]["status"] == "failed"
        assert pool.indexes[failing.index_id]["last_error"] == "storage unavailable"

    asyncio.run(scenario())


def test_gc_reclaims_expired_deleting_lease_after_storage_delete_crash() -> None:
    async def scenario() -> None:
        pool = FakeRegistryPool()
        pool.add_repository("repo")
        repo = registry(pool)
        expired = NOW - timedelta(days=1)
        candidate = await repo.ensure_index(
            identity(kind=NamespaceKind.FEATURE, key="feature/crashed"),
            retention_until=expired,
        )
        row = pool.indexes[candidate.index_id]
        row.update(
            status="deleting",
            lease_token=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
            lease_owner="crashed-gc",
            lease_expires_at=NOW - timedelta(seconds=1),
        )
        storage_that_still_exists: set[str] = set()
        delete_calls: list[str] = []

        async def idempotent_delete(storage_key: str) -> None:
            delete_calls.append(storage_key)
            storage_that_still_exists.discard(storage_key)

        result = await repo.collect_garbage(idempotent_delete)

        assert result == GarbageCollectionResult(
            deleted=(candidate.index_id,), failed=()
        )
        assert delete_calls == [candidate.storage_key]
        assert pool.indexes[candidate.index_id]["status"] == "deleted"
        assert pool.indexes[candidate.index_id]["deleted_at"] == NOW

    asyncio.run(scenario())


async def make_ready(repo: SemanticIndexRegistry, index_id: UUID):
    claimed = await repo.claim_index(
        index_id, lease_owner="worker", lease_duration=timedelta(minutes=5)
    )
    return await repo.mark_ready(index_id, claimed.lease_token, chunk_count=1)
