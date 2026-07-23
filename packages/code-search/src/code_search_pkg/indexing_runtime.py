"""Light, dependency-injected orchestration for durable semantic indexing.

This module owns lifecycle ordering, not source enumeration, provider
construction, or CLI parsing. Heavy indexing implementations are injected at
the boundary so importing registry and exact-search paths remains cheap.
"""

from __future__ import annotations

from uuid import UUID

from .embedding_protocol import EmbeddingProviderError, EmbeddingReadinessState
from .indexing_runtime_models import (
    BuildPlan as BuildPlan,
    CheckReadiness as CheckReadiness,
    GitAncestry as GitAncestry,
    IndexBuildPlan as IndexBuildPlan,
    IndexExecutionCounts as IndexExecutionCounts,
    IndexExecutionError as IndexExecutionError,
    IndexExecutionRequest as IndexExecutionRequest,
    IndexExecutionResult as IndexExecutionResult,
    IndexExecutionStatus as IndexExecutionStatus,
    IndexProcessResult as IndexProcessResult,
    IndexRegistry as IndexRegistry,
    IndexStorage as IndexStorage,
    LeaseGuard,
    ProcessChanged as ProcessChanged,
    ProofSource as ProofSource,
    VerifySource as VerifySource,
    await_maybe,
    best_effort_cleanup,
    safe_source_message,
)
from .indexing_runtime_results import (
    LEASE_CONFLICT_MESSAGE,
    conflict_result,
    durable_result,
    ephemeral_failure,
    error_result,
    merge_manifest,
    success_result,
)
from .registry_models import (
    IndexIdentity,
    IndexLeaseConflictError,
    IndexStateConflictError,
    IndexStatus,
    NamespaceKind,
    SemanticIndexRecord,
)
from .source_proof import SourceProof, SourceProofError
from .source_manifest import SourceManifestError
from .storage_pg import StorageAttempt


_SAFE_FAILURE_MESSAGE = "semantic indexing failed; inspect sanitized operation logs"


class IndexingRuntime:
    """Execute one exact-revision operation through its durable lifecycle."""

    def __init__(
        self,
        *,
        registry: IndexRegistry,
        storage: IndexStorage,
        prove_source: ProofSource,
        verify_source: VerifySource,
        check_embedding_readiness: CheckReadiness,
        is_git_ancestor: GitAncestry,
        build_plan: BuildPlan,
        process_changed: ProcessChanged,
        heartbeat_interval: float | None = None,
    ) -> None:
        self._registry = registry
        self._storage = storage
        self._prove_source = prove_source
        self._verify_source = verify_source
        self._check_embedding_readiness = check_embedding_readiness
        self._is_git_ancestor = is_git_ancestor
        self._build_plan = build_plan
        self._process_changed = process_changed
        if heartbeat_interval is not None and heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")
        self._heartbeat_interval = heartbeat_interval

    async def execute(self, request: IndexExecutionRequest) -> IndexExecutionResult:
        """Run the operation, mapping every exit to the public result contract."""

        identity = request.identity
        try:
            existing = await self._registry.find_index(identity)
        except Exception:
            return ephemeral_failure(identity)
        if existing is not None and existing.status is IndexStatus.READY:
            return await self._ready_result(existing, reused=True)

        try:
            proof = await await_maybe(self._prove_source(request))
        except SourceProofError as error:
            return ephemeral_failure(
                identity,
                code=error.code,
                message=safe_source_message(error),
            )
        except Exception:
            return ephemeral_failure(identity)

        try:
            record = await self._registry.ensure_index(
                identity,
                retention_until=request.retention_until,
            )
        except Exception:
            return ephemeral_failure(identity)
        if record.status is IndexStatus.READY:
            return await self._ready_result(record, reused=True)

        claimed_or_result = await self._claim(request, record)
        if isinstance(claimed_or_result, IndexExecutionResult):
            return claimed_or_result
        claimed = claimed_or_result
        guard = LeaseGuard(
            self._registry,
            claimed,
            request.lease_duration,
            interval=self._heartbeat_interval,
        )
        await guard.start()
        try:
            return await self._execute_claimed(
                request,
                claimed,
                proof,
                guard,
            )
        finally:
            await guard.stop()

    async def _claim(
        self,
        request: IndexExecutionRequest,
        record: SemanticIndexRecord,
    ) -> SemanticIndexRecord | IndexExecutionResult:
        try:
            return await self._registry.claim_index(
                record.index_id,
                lease_owner=request.lease_owner,
                lease_duration=request.lease_duration,
            )
        except IndexStateConflictError:
            try:
                current = await self._registry.get_index(record.index_id)
            except Exception:
                current = record
            if current.status is IndexStatus.READY:
                return await self._ready_result(current, reused=True)
            return error_result(
                current,
                IndexExecutionStatus.CONFLICT,
                "lease_conflict",
                LEASE_CONFLICT_MESSAGE,
            )
        except Exception:
            return error_result(
                record,
                IndexExecutionStatus.FAILED,
                "registry_unavailable",
                "the durable index operation could not be claimed",
            )

    async def _execute_claimed(
        self,
        request: IndexExecutionRequest,
        claimed: SemanticIndexRecord,
        proof: SourceProof,
        guard: LeaseGuard,
    ) -> IndexExecutionResult:
        attempt: StorageAttempt | None = None
        published = False
        try:
            readiness_result = await self._handle_readiness(claimed, guard)
            if isinstance(readiness_result, IndexExecutionResult):
                return readiness_result

            parent, claimed = await self._select_parent(
                request,
                claimed,
                guard,
            )
            expected_canonical = await self._expected_canonical(
                request.identity,
                guard,
            )
            parent_manifest = (
                await guard.run(self._registry.get_published_manifest(parent.index_id))
                if parent is not None
                else ()
            )
            plan = await guard.run(
                await_maybe(self._build_plan(proof, parent, parent_manifest))
            )
            attempt = await guard.run(
                self._storage.prepare_attempt(
                    claimed,
                    embedding_dim=request.identity.embedding_dim,
                )
            )
            if parent is not None and plan.unchanged_paths:
                await guard.run(
                    self._storage.copy_unchanged(
                        parent.storage_key,
                        attempt,
                        plan.unchanged_paths,
                    )
                )
            processed = await self._process(plan, attempt, guard)
            entries = merge_manifest(plan, processed)
            await guard.run(
                self._registry.replace_attempt_manifest(
                    claimed.index_id,
                    claimed.lease_token,
                    claimed.attempt_count,
                    entries,
                )
            )
            expected_chunks = sum(
                entry.chunk_count for entry in entries if entry.eligible
            )
            expected_files = sum(
                1 for entry in entries if entry.eligible and entry.chunk_count > 0
            )
            await guard.run(
                self._storage.verify_attempt(
                    attempt,
                    expected_chunks=expected_chunks,
                    expected_files=expected_files,
                )
            )
            await guard.run(await_maybe(self._verify_source(proof)))
            await guard.run(self._storage.publish_attempt(claimed, attempt))
            published = True
            ready = await guard.run(
                self._registry.mark_ready(
                    claimed.index_id,
                    claimed.lease_token,
                    chunk_count=expected_chunks,
                )
            )
            promoted = await self._promote(
                ready,
                expected_canonical=expected_canonical,
            )
            return success_result(
                ready,
                plan,
                processed,
                entries,
                parent=parent,
                promoted=promoted,
            )
        except IndexLeaseConflictError:
            if attempt is not None and not published:
                await best_effort_cleanup(self._storage, attempt)
            return conflict_result(claimed)
        except SourceProofError as error:
            if attempt is not None and not published:
                await best_effort_cleanup(self._storage, attempt)
            return await self._durable_failure(
                claimed,
                code=error.code,
                message=safe_source_message(error),
            )
        except SourceManifestError as error:
            if attempt is not None and not published:
                await best_effort_cleanup(self._storage, attempt)
            return await self._durable_failure(
                claimed,
                code=error.code,
                message=str(error),
            )
        except EmbeddingProviderError as error:
            if attempt is not None and not published:
                await best_effort_cleanup(self._storage, attempt)
            return await self._durable_failure(
                claimed,
                code=(
                    error.error_code.value
                    if error.error_code is not None
                    else "provider_failure"
                ),
                message=error.safe_message or "embedding provider failed",
            )
        except Exception:
            if attempt is not None and not published:
                await best_effort_cleanup(self._storage, attempt)
            return await self._durable_failure(
                claimed,
                code="indexing_failed",
                message=_SAFE_FAILURE_MESSAGE,
            )

    async def _handle_readiness(
        self,
        record: SemanticIndexRecord,
        guard: LeaseGuard,
    ) -> None | IndexExecutionResult:
        readiness = await guard.run(self._check_embedding_readiness())
        if readiness.state is EmbeddingReadinessState.READY:
            return None
        code = (
            readiness.error_code.value
            if readiness.error_code is not None
            else "embedding_unavailable"
        )
        message = readiness.safe_message or "embedding provider is unavailable"
        if readiness.state is EmbeddingReadinessState.NOT_CONFIGURED:
            await guard.run(
                self._registry.mark_not_configured(
                    record.index_id,
                    record.lease_token,
                    message,
                )
            )
            return error_result(
                record,
                IndexExecutionStatus.NOT_CONFIGURED,
                code,
                message,
            )
        await guard.run(
            self._registry.mark_failed(
                record.index_id,
                record.lease_token,
                message,
            )
        )
        return error_result(
            record,
            IndexExecutionStatus.FAILED,
            code,
            message,
        )

    async def _select_parent(
        self,
        request: IndexExecutionRequest,
        record: SemanticIndexRecord,
        guard: LeaseGuard,
    ) -> tuple[SemanticIndexRecord | None, SemanticIndexRecord]:
        if request.full_rebuild:
            return None, record
        candidates = await guard.run(
            self._registry.find_compatible_parents(
                request.identity,
                limit=request.parent_candidate_limit,
            )
        )
        for candidate in candidates:
            is_ancestor = await guard.run(
                await_maybe(
                    self._is_git_ancestor(
                        candidate.source_revision,
                        request.identity.source_revision,
                    )
                )
            )
            if is_ancestor:
                linked = await guard.run(
                    self._registry.set_parent_index(
                        record.index_id,
                        record.lease_token,
                        candidate.index_id,
                    )
                )
                return candidate, linked
        return None, record

    async def _process(
        self,
        plan: IndexBuildPlan,
        attempt: StorageAttempt,
        guard: LeaseGuard,
    ) -> IndexProcessResult:
        if not plan.changed_paths:
            return IndexProcessResult(entries=(), embedded_chunks=0)
        result = await guard.run(
            await_maybe(self._process_changed(attempt, plan.changed_paths))
        )
        returned_paths = {entry.file_path for entry in result.entries}
        if returned_paths != set(plan.changed_paths):
            raise RuntimeError(
                "pipeline manifest does not cover every changed path exactly"
            )
        measured_chunks = sum(entry.chunk_count for entry in result.entries)
        if measured_chunks != result.embedded_chunks:
            raise RuntimeError("pipeline embedded chunk count is inconsistent")
        return result

    async def _expected_canonical(
        self,
        identity: IndexIdentity,
        guard: LeaseGuard,
    ) -> UUID | None:
        if identity.namespace_kind is not NamespaceKind.MAIN:
            return None
        return await guard.run(
            self._registry.get_canonical_index_id(identity.repo_slug)
        )

    async def _promote(
        self,
        ready: SemanticIndexRecord,
        *,
        expected_canonical: UUID | None,
    ) -> bool:
        if ready.namespace_kind is not NamespaceKind.MAIN:
            return False
        try:
            await self._registry.promote_canonical(
                ready.repo_slug,
                ready.index_id,
                expected_current_index_id=expected_canonical,
            )
        except Exception:
            return False
        return True

    async def _ready_result(
        self,
        record: SemanticIndexRecord,
        *,
        reused: bool,
    ) -> IndexExecutionResult:
        parent = None
        if record.parent_index_id is not None:
            try:
                parent = await self._registry.get_index(record.parent_index_id)
            except Exception:
                pass
        return durable_result(
            record,
            IndexExecutionStatus.READY,
            reused=reused,
            parent=parent,
            counts=IndexExecutionCounts(chunks=record.chunk_count or 0),
        )

    async def _durable_failure(
        self,
        record: SemanticIndexRecord,
        *,
        code: str,
        message: str,
    ) -> IndexExecutionResult:
        try:
            await self._registry.mark_failed(
                record.index_id,
                record.lease_token,
                message,
            )
        except IndexLeaseConflictError:
            return conflict_result(record)
        except Exception:
            code = "registry_unavailable"
            message = "the durable operation could not record its terminal failure"
        return error_result(
            record,
            IndexExecutionStatus.FAILED,
            code,
            message,
        )
