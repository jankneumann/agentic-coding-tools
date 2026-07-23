from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from code_search_pkg.embedding_protocol import (
    EmbeddingErrorCode,
    EmbeddingProviderError,
    EmbeddingReadiness,
)
from code_search_pkg.indexing_runtime import (
    IndexBuildPlan,
    IndexExecutionRequest,
    IndexProcessResult,
    IndexingRuntime,
)
from code_search_pkg.registry_models import (
    CanonicalPromotionError,
    FileManifestEntry,
    IndexIdentity,
    IndexLeaseConflictError,
    IndexStateConflictError,
    IndexStatus,
    NamespaceKind,
    SemanticIndexRecord,
)
from code_search_pkg.source_proof import SourceProof, SourceProofError
from code_search_pkg.source_manifest import SourceManifestError
from code_search_pkg.storage_pg import StorageAttempt, StorageVerification


NOW = datetime(2026, 7, 23, tzinfo=UTC)
INDEX_ID = UUID("11111111-1111-4111-8111-111111111111")
PARENT_ID = UUID("22222222-2222-4222-8222-222222222222")
LEASE = UUID("33333333-3333-4333-8333-333333333333")
IDENTITY = IndexIdentity(
    repo_slug="repo",
    namespace_kind=NamespaceKind.MAIN,
    namespace_key="main",
    source_revision="b" * 40,
    embedder_model="model",
    embedding_dim=3,
    policy_fingerprint="1" * 64,
    pipeline_fingerprint="2" * 64,
    embedder_fingerprint="3" * 64,
)
PROOF = SourceProof("/repo", "b" * 40, "4" * 64, "5" * 64)


def make_record(
    *,
    index_id: UUID = INDEX_ID,
    revision: str = "b" * 40,
    status: IndexStatus = IndexStatus.PENDING,
    attempt_count: int = 0,
    lease_token: UUID | None = None,
    parent_index_id: UUID | None = None,
    chunk_count: int | None = None,
) -> SemanticIndexRecord:
    leased = status is IndexStatus.INDEXING
    completed = NOW if status is IndexStatus.READY else None
    return SemanticIndexRecord(
        index_id=index_id,
        storage_key=f"i_{index_id.hex}",
        repo_slug="repo",
        namespace_kind=NamespaceKind.MAIN,
        namespace_key="main",
        source_revision=revision,
        embedder_model="model",
        embedding_dim=3,
        policy_fingerprint="1" * 64,
        pipeline_fingerprint="2" * 64,
        embedder_fingerprint="3" * 64,
        parent_index_id=parent_index_id,
        status=status,
        attempt_count=attempt_count,
        chunk_count=chunk_count,
        last_error=None,
        lease_token=lease_token,
        lease_owner="worker" if leased else None,
        lease_expires_at=NOW + timedelta(minutes=5) if leased else None,
        retention_until=None,
        started_at=NOW if attempt_count else None,
        completed_at=completed,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def manifest(path: str, *, chunks: int = 1) -> FileManifestEntry:
    return FileManifestEntry(
        file_path=path,
        git_blob_id="a" * 40,
        git_entry_type="blob",
        eligible=True,
        eligibility_reason="eligible",
        content_digest="6" * 64,
        chunk_digest="7" * 64,
        chunk_count=chunks,
    )


class FakeRegistry:
    def __init__(self, existing: SemanticIndexRecord | None = None) -> None:
        self.existing = existing
        self.claimed = make_record(
            status=IndexStatus.INDEXING,
            attempt_count=1,
            lease_token=LEASE,
        )
        self.parent = make_record(
            index_id=PARENT_ID,
            revision="a" * 40,
            status=IndexStatus.READY,
            attempt_count=1,
            chunk_count=1,
        )
        self.calls: list[str] = []
        self.claim_error: Exception | None = None
        self.renew_error: Exception | None = None
        self.marked_error: str | None = None
        self.canonical_id: UUID | None = None

    async def find_index(self, identity):
        self.calls.append("find")
        return self.existing

    async def ensure_index(self, identity, *, retention_until=None):
        self.calls.append("ensure")
        return self.existing or make_record()

    async def claim_index(self, index_id, *, lease_owner, lease_duration):
        self.calls.append("claim")
        if self.claim_error:
            raise self.claim_error
        return self.claimed

    async def get_index(self, index_id):
        self.calls.append("get")
        if index_id == PARENT_ID:
            return self.parent
        return self.existing or self.claimed

    async def renew_index_lease(self, index_id, lease_token, lease_duration):
        self.calls.append("renew")
        if self.renew_error:
            raise self.renew_error
        return self.claimed

    async def find_compatible_parents(self, identity, *, limit=20):
        self.calls.append("parents")
        return (self.parent,)

    async def set_parent_index(self, index_id, lease_token, parent_index_id):
        self.calls.append("set_parent")
        self.claimed = replace(self.claimed, parent_index_id=parent_index_id)
        return self.claimed

    async def get_published_manifest(self, index_id):
        self.calls.append("parent_manifest")
        return (manifest("src/old.py"),)

    async def replace_attempt_manifest(
        self, index_id, lease_token, attempt_count, entries
    ):
        self.calls.append("manifest")
        return tuple(entries)

    async def get_canonical_index_id(self, repo_slug):
        self.calls.append("canonical")
        return self.canonical_id

    async def mark_ready(self, index_id, lease_token, *, chunk_count):
        self.calls.append("ready")
        self.existing = replace(
            self.claimed,
            status=IndexStatus.READY,
            lease_token=None,
            lease_owner=None,
            lease_expires_at=None,
            chunk_count=chunk_count,
            completed_at=NOW,
        )
        return self.existing

    async def mark_failed(self, index_id, lease_token, error):
        self.calls.append("failed")
        self.marked_error = error
        return self.claimed

    async def mark_not_configured(self, index_id, lease_token, reason):
        self.calls.append("not_configured")
        self.marked_error = reason
        return self.claimed

    async def promote_canonical(
        self, repo_slug, index_id, *, expected_current_index_id
    ):
        self.calls.append("promote")
        if self.canonical_id != expected_current_index_id:
            raise CanonicalPromotionError("stale canonical")
        self.canonical_id = index_id
        return index_id


class FakeStorage:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.verify_error: Exception | None = None
        self.expected_verification: tuple[int, int] | None = None
        self.attempt = StorageAttempt(
            INDEX_ID,
            1,
            f"i_{INDEX_ID.hex}",
            f"ccs__{INDEX_ID.hex}__1",
            f"ccs__{INDEX_ID.hex}",
            3,
        )

    async def prepare_attempt(self, record, *, embedding_dim):
        self.calls.append("prepare")
        return self.attempt

    async def copy_unchanged(self, parent_storage_key, attempt, paths):
        self.calls.append("copy")
        return len(paths)

    async def verify_attempt(self, attempt, *, expected_chunks, expected_files):
        self.calls.append("verify")
        self.expected_verification = (expected_chunks, expected_files)
        if self.verify_error:
            raise self.verify_error
        return StorageVerification(
            expected_chunks,
            expected_files,
            True,
            True,
            True,
        )

    async def publish_attempt(self, record, attempt):
        self.calls.append("publish")

    async def cleanup_attempt(self, attempt):
        self.calls.append("cleanup")


class Harness:
    def __init__(
        self,
        registry: FakeRegistry | None = None,
        storage: FakeStorage | None = None,
    ) -> None:
        self.registry = registry or FakeRegistry()
        self.storage = storage or FakeStorage()
        self.calls: list[str] = []
        self.readiness = EmbeddingReadiness.ready()
        self.process_gate: asyncio.Event | None = None
        self.process_chunks: dict[str, int] = {}
        self.plan = IndexBuildPlan(
            entries=(manifest("src/old.py"),),
            unchanged_paths=("src/old.py",),
            changed_paths=("src/new.py",),
            removed_files=1,
        )

    async def prove(self, request):
        self.calls.append("prove")
        return PROOF

    async def reprove(self, proof):
        self.calls.append("reprove")
        return proof

    async def check_readiness(self):
        self.calls.append("readiness")
        return self.readiness

    async def is_ancestor(self, parent, child):
        self.calls.append("ancestry")
        return True

    async def build_plan(self, proof, parent, parent_manifest):
        self.calls.append("plan")
        return self.plan

    async def process(self, attempt, changed_paths):
        self.calls.append("process")
        if self.process_gate is not None:
            await self.process_gate.wait()
        entries = tuple(
            manifest(path, chunks=self.process_chunks.get(path, 2))
            for path in changed_paths
        )
        return IndexProcessResult(
            entries=entries,
            embedded_chunks=sum(entry.chunk_count for entry in entries),
        )

    def runtime(self, *, heartbeat_interval=3600.0):
        return IndexingRuntime(
            registry=self.registry,
            storage=self.storage,
            prove_source=self.prove,
            verify_source=self.reprove,
            check_embedding_readiness=self.check_readiness,
            is_git_ancestor=self.is_ancestor,
            build_plan=self.build_plan,
            process_changed=self.process,
            heartbeat_interval=heartbeat_interval,
        )

    def request(self, **overrides):
        return replace(
            IndexExecutionRequest(
                identity=IDENTITY,
                repo_root="/repo",
                lease_owner="worker",
                lease_duration=timedelta(minutes=5),
            ),
            **overrides,
        )


@pytest.mark.asyncio
async def test_ready_short_circuit_precedes_source_read_and_storage():
    ready = make_record(
        status=IndexStatus.READY,
        attempt_count=1,
        chunk_count=4,
    )
    harness = Harness(FakeRegistry(existing=ready))

    result = await harness.runtime().execute(harness.request())

    assert result.status == "ready"
    assert result.reused is True
    assert result.counts.chunks == 4
    assert harness.calls == []
    assert harness.storage.calls == []


@pytest.mark.asyncio
async def test_ready_duplicate_retries_safe_canonical_promotion():
    ready = make_record(
        status=IndexStatus.READY,
        attempt_count=1,
        parent_index_id=PARENT_ID,
        chunk_count=4,
    )
    registry = FakeRegistry(existing=ready)
    registry.canonical_id = PARENT_ID
    harness = Harness(registry)

    result = await harness.runtime().execute(harness.request())

    assert result.status == "ready"
    assert result.reused is True
    assert result.promoted is True
    assert registry.canonical_id == INDEX_ID
    assert harness.calls == []
    assert harness.storage.calls == []


@pytest.mark.asyncio
async def test_ready_duplicate_does_not_replace_unrelated_canonical_index():
    ready = make_record(
        status=IndexStatus.READY,
        attempt_count=1,
        parent_index_id=PARENT_ID,
        chunk_count=4,
    )
    registry = FakeRegistry(existing=ready)
    registry.canonical_id = UUID("99999999-9999-4999-8999-999999999999")
    harness = Harness(registry)

    result = await harness.runtime().execute(harness.request())

    assert result.status == "ready"
    assert result.promoted is False
    assert "promote" not in registry.calls
    assert registry.canonical_id != INDEX_ID


@pytest.mark.asyncio
async def test_active_claim_conflict_returns_shared_durable_identity():
    harness = Harness()
    harness.registry.claim_error = IndexStateConflictError("actively leased")

    result = await harness.runtime().execute(harness.request())

    assert (result.status, result.durable, result.index_id) == (
        "conflict",
        True,
        INDEX_ID,
    )
    assert "process" not in harness.calls


@pytest.mark.asyncio
async def test_expired_indexing_record_is_claimed_for_a_new_attempt():
    expired = make_record(
        status=IndexStatus.INDEXING,
        attempt_count=1,
        lease_token=UUID("44444444-4444-4444-8444-444444444444"),
    )
    expired = replace(
        expired,
        lease_expires_at=NOW - timedelta(seconds=1),
    )
    harness = Harness(FakeRegistry(existing=expired))

    result = await harness.runtime().execute(harness.request())

    assert result.status == "ready"
    assert harness.registry.calls.count("claim") == 1
    assert harness.registry.claimed.attempt_count == 1


@pytest.mark.asyncio
async def test_ready_build_selects_ancestor_copies_and_promotes_main():
    harness = Harness()

    result = await harness.runtime().execute(harness.request())

    assert result.status == "ready"
    assert result.parent_index_id == PARENT_ID
    assert result.parent_revision == "a" * 40
    assert result.promoted is True
    assert result.counts.copied_files == 1
    assert result.counts.changed_files == 1
    assert result.counts.embedded_chunks == 2
    assert harness.storage.calls == ["prepare", "copy", "verify", "publish"]
    assert "manifest" in harness.registry.calls
    assert harness.calls.index("reprove") > harness.calls.index("process")
    assert harness.registry.calls[-2:] == ["ready", "promote"]


@pytest.mark.asyncio
async def test_full_rebuild_disables_parent_reuse_and_feature_is_not_promoted():
    harness = Harness()
    identity = replace(
        IDENTITY,
        namespace_kind=NamespaceKind.FEATURE,
        namespace_key="feature/x",
    )
    harness.registry.claimed = replace(
        harness.registry.claimed,
        namespace_kind=NamespaceKind.FEATURE,
        namespace_key="feature/x",
    )
    harness.plan = replace(
        harness.plan,
        entries=(),
        unchanged_paths=(),
        changed_paths=("src/old.py", "src/new.py"),
    )

    result = await harness.runtime().execute(
        replace(harness.request(full_rebuild=True), identity=identity)
    )

    assert result.status == "ready"
    assert result.parent_index_id is None
    assert result.promoted is False
    assert "parents" not in harness.registry.calls
    assert "copy" not in harness.storage.calls
    assert "promote" not in harness.registry.calls


@pytest.mark.asyncio
async def test_not_configured_is_persisted_with_sanitized_error():
    harness = Harness()
    harness.readiness = EmbeddingReadiness.not_configured(
        EmbeddingErrorCode.MISSING_CREDENTIAL,
        "credential reference is unavailable",
    )

    result = await harness.runtime().execute(harness.request())

    assert result.status == "not_configured"
    assert result.durable is True
    assert result.error is not None
    assert result.error.code == "missing_credential"
    assert harness.registry.calls[-1] == "not_configured"
    assert harness.registry.marked_error == "credential reference is unavailable"


@pytest.mark.asyncio
async def test_source_failure_before_ensure_is_ephemeral_and_sanitized():
    harness = Harness()

    async def fail_proof(request):
        raise SourceProofError("source_dirty", "worktree is not clean")

    harness.prove = fail_proof

    result = await harness.runtime().execute(harness.request())

    assert result.status == "failed"
    assert result.durable is False
    assert result.error is not None
    assert result.error.code == "source_dirty"
    assert "ensure" not in harness.registry.calls


@pytest.mark.asyncio
async def test_source_mutation_marks_claimed_operation_failed_and_cleans_attempt():
    harness = Harness()

    async def fail_reproof(proof):
        raise SourceProofError("source_proof_lost", "source changed")

    harness.reprove = fail_reproof

    result = await harness.runtime().execute(harness.request())

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "source_proof_lost"
    assert "failed" in harness.registry.calls
    assert harness.storage.calls[-1] == "cleanup"


@pytest.mark.asyncio
async def test_runtime_exception_is_sanitized_before_durable_failure():
    harness = Harness()

    async def fail_process(attempt, changed_paths):
        raise RuntimeError("secret token sk-live-must-not-leak")

    harness.process = fail_process

    result = await harness.runtime().execute(harness.request())

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "indexing_failed"
    assert "sk-live" not in result.error.message
    assert "sk-live" not in (harness.registry.marked_error or "")
    assert harness.storage.calls[-1] == "cleanup"


@pytest.mark.asyncio
async def test_source_manifest_failure_preserves_sanitized_actionable_code():
    harness = Harness()

    async def fail_plan(proof, parent, parent_manifest):
        raise SourceManifestError(
            "secret_scan_failed",
            "local secret scan failed while planning source files",
        )

    harness.build_plan = fail_plan

    result = await harness.runtime().execute(harness.request())

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "secret_scan_failed"
    assert result.error.message == (
        "local secret scan failed while planning source files"
    )
    assert harness.registry.marked_error == result.error.message


@pytest.mark.asyncio
async def test_embedding_runtime_failure_preserves_provider_taxonomy():
    harness = Harness()

    async def fail_process(attempt, changed_paths):
        raise EmbeddingProviderError(
            EmbeddingErrorCode.PROVIDER_FAILURE,
            "embedding provider request failed",
        )

    harness.process = fail_process

    result = await harness.runtime().execute(harness.request())

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "provider_failure"
    assert result.error.message == "embedding provider request failed"


@pytest.mark.asyncio
async def test_storage_verification_failure_is_durable_and_cleans_attempt():
    harness = Harness()
    harness.storage.verify_error = RuntimeError("coverage mismatch")

    result = await harness.runtime().execute(harness.request())

    assert result.status == "failed"
    assert harness.registry.calls[-1] == "failed"
    assert harness.storage.calls[-1] == "cleanup"


@pytest.mark.asyncio
async def test_zero_chunk_changed_file_has_final_manifest_but_no_storage_file():
    harness = Harness()
    harness.plan = IndexBuildPlan(
        entries=(),
        unchanged_paths=(),
        changed_paths=("src/empty.py",),
    )
    harness.process_chunks["src/empty.py"] = 0

    result = await harness.runtime().execute(harness.request())

    assert result.status == "ready"
    assert result.counts.changed_files == 1
    assert result.counts.chunks == 0
    assert harness.storage.expected_verification == (0, 0)


@pytest.mark.asyncio
async def test_heartbeat_renews_lease_during_processing():
    harness = Harness()
    harness.process_gate = asyncio.Event()
    operation = asyncio.create_task(
        harness.runtime(heartbeat_interval=0.001).execute(harness.request())
    )

    for _ in range(100):
        if "renew" in harness.registry.calls:
            break
        await asyncio.sleep(0.001)
    harness.process_gate.set()
    result = await asyncio.wait_for(operation, timeout=1)

    assert result.status == "ready"
    assert "renew" in harness.registry.calls


@pytest.mark.asyncio
async def test_heartbeat_loss_cancels_processing_and_returns_conflict():
    harness = Harness()
    harness.process_gate = asyncio.Event()
    harness.registry.renew_error = IndexLeaseConflictError("replaced")

    result = await asyncio.wait_for(
        harness.runtime(heartbeat_interval=0.001).execute(harness.request()),
        timeout=1,
    )

    assert result.status == "conflict"
    assert "failed" not in harness.registry.calls
    assert harness.storage.calls[-1] == "cleanup"


@pytest.mark.asyncio
async def test_canonical_compare_and_swap_failure_leaves_ready_unpromoted():
    harness = Harness()

    async def fail_promotion(*args, **kwargs):
        raise CanonicalPromotionError("stale canonical")

    harness.registry.promote_canonical = fail_promotion

    result = await harness.runtime().execute(harness.request())

    assert result.status == "ready"
    assert result.promoted is False
    assert result.error is None
