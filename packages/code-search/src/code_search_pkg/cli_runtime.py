# pyright: reportMissingImports=false
"""Concrete runtime assembly loaded only after CLI preflight succeeds."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any


async def create_pool(dsn: str) -> Any:
    import asyncpg

    return await asyncpg.create_pool(dsn)


def registry_factory(pool: Any) -> Any:
    from .registry import SemanticIndexRegistry

    return SemanticIndexRegistry(pool)


def storage_factory(pool: Any, *, manifest_publisher: Any) -> Any:
    from .storage_pg import StoragePublisher

    return StoragePublisher(pool, manifest_publisher=manifest_publisher)


def provider_factory(contract: Any, **kwargs: Any) -> Any:
    from .embedding_config import build_embedding_provider

    return build_embedding_provider(contract, **kwargs)


def resolve_cocoindex_state_path(
    *,
    repo_root: Path,
    git_common_dir: Path,
    environment: Mapping[str, str],
    app_name: str,
) -> Path:
    """Choose durable CocoIndex memo state without dirtying the source tree."""

    override = environment.get("CODE_SEARCH_COCOINDEX_STATE_DIR")
    if override:
        base = Path(override).expanduser().resolve(strict=False)
        try:
            base.relative_to(repo_root)
        except ValueError:
            pass
        else:
            raise ValueError(
                "CocoIndex state override must be outside the source worktree"
            )
    else:
        base = git_common_dir / "code-search-cocoindex"
    return base / app_name


async def ensure_repository(
    pool: Any,
    repo_slug: str,
    repo_root: Path,
    embedder_model: str,
    embedding_dim: int,
    git_common_dir_fingerprint: str,
) -> None:
    """Compatibility seam delegating identity ownership to the registry API."""

    from .registry import SemanticIndexRegistry
    from .registry_models import RepositoryIdentity

    await SemanticIndexRegistry(pool).ensure_repository_identity(
        RepositoryIdentity(
            repo_slug,
            str(repo_root.resolve()),
            git_common_dir_fingerprint,
        ),
        embedder_model=embedder_model,
        embedding_dim=embedding_dim,
    )


async def execute_operation(context: Any) -> Any:
    """Assemble source planning, CocoIndex processing, and durable runtime."""

    from .indexing_runtime import (
        IndexBuildPlan,
        IndexProcessResult,
        IndexingRuntime,
    )
    from .registry_models import (
        FileManifestEntry,
        IndexNotFoundError,
        RepositoryIdentity,
        RepositoryIdentityConflictError,
    )
    from .secret_scanner import LocalSecretScanner
    from .source_manifest import SourceFilePlan, build_source_manifest
    from .source_proof import (
        SourceProofError,
        prove_source,
        verify_source_unchanged,
    )

    scanner = LocalSecretScanner()
    changed_metadata: dict[str, SourceFilePlan] = {}
    proven_git_common_dir: Path | None = None

    async def prove(request: Any) -> Any:
        nonlocal proven_git_common_dir
        try:
            registered = await context.registry.get_repository_identity(
                request.identity.repo_slug
            )
        except IndexNotFoundError:
            registered = None
        proof = await asyncio.to_thread(
            prove_source,
            request.repo_root,
            request.identity.source_revision,
            registered_repo_root=(None if registered is None else registered.repo_root),
            registered_git_common_dir_fingerprint=(
                None
                if registered is None or registered.is_legacy
                else registered.git_common_dir_fingerprint
            ),
        )
        if registered is None or registered.is_legacy:
            try:
                await context.registry.ensure_repository_identity(
                    RepositoryIdentity(
                        request.identity.repo_slug,
                        proof.repo_root,
                        proof.git_common_dir_fingerprint,
                    ),
                    embedder_model=request.identity.embedder_model,
                    embedding_dim=request.identity.embedding_dim,
                )
            except RepositoryIdentityConflictError as error:
                raise SourceProofError(
                    "repository_identity_mismatch",
                    "repository identity does not match registered metadata",
                ) from error
        proven_git_common_dir = _git_common_dir(context.repo_root)
        return proof

    def ancestry(parent_revision: str, child_revision: str) -> bool:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(context.repo_root),
                "merge-base",
                "--is-ancestor",
                parent_revision,
                child_revision,
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if result.returncode not in {0, 1}:
            raise RuntimeError("Git ancestry check failed")
        return result.returncode == 0

    async def build_plan(
        proof: Any,
        parent: Any,
        parent_manifest: tuple[Any, ...],
    ) -> Any:
        del parent
        source_plan = await asyncio.to_thread(
            build_source_manifest,
            context.repo_root,
            proof.source_revision,
            context.policy,
            scanner,
            parent_manifest=parent_manifest,
        )
        entries: list[FileManifestEntry] = []
        changed_metadata.clear()
        for file_plan in source_plan.files:
            if file_plan.disposition == "changed":
                changed_metadata[file_plan.path] = file_plan
                continue
            entry_type = (
                file_plan.git_entry_type
                if file_plan.git_entry_type in {"blob", "symlink"}
                else None
            )
            entries.append(
                FileManifestEntry(
                    file_path=file_plan.path,
                    git_blob_id=file_plan.git_blob_id,
                    git_entry_type=entry_type,
                    eligible=file_plan.eligible,
                    eligibility_reason=file_plan.eligibility_reason,
                    content_digest=file_plan.content_digest,
                    chunk_digest=file_plan.parent_chunk_digest,
                    chunk_count=file_plan.parent_chunk_count or 0,
                )
            )
        return IndexBuildPlan(
            entries=tuple(entries),
            unchanged_paths=source_plan.copied_paths,
            changed_paths=source_plan.changed_paths,
            removed_files=len(source_plan.removed_paths),
        )

    async def process_changed(attempt: Any, changed_paths: tuple[str, ...]) -> Any:
        from .embedding_config import CocoIndexSingleTextEmbedder
        from .indexer_pg import PipelineConfig, run_pipeline, stable_app_name

        if proven_git_common_dir is None:
            raise RuntimeError("CocoIndex state requires a proven Git repository")
        app_name = stable_app_name(
            context.request.identity.repo_slug,
            context.request.identity.namespace_kind.value,
            context.request.identity.namespace_key,
            context.pipeline_fingerprint,
        )
        state_path = resolve_cocoindex_state_path(
            repo_root=context.repo_root,
            git_common_dir=proven_git_common_dir,
            environment=context.environment,
            app_name=app_name,
        )
        state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        content_digests: dict[str, str] = {}
        for path in changed_paths:
            digest = changed_metadata[path].content_digest
            if digest is None:
                raise RuntimeError("changed source file is missing its Git blob digest")
            content_digests[path] = digest
        config = PipelineConfig(
            app_name=app_name,
            cocoindex_state_path=state_path,
            repo_root=context.repo_root,
            changed_paths=changed_paths,
            expected_content_digests=content_digests,
            pipeline_fingerprint=context.pipeline_fingerprint,
            storage_publisher=context.storage,
            storage_attempt=attempt,
            embedder=CocoIndexSingleTextEmbedder(context.provider),
            indexing_parameters=dict(context.provider.indexing_parameters),
            secret_scanner=scanner,
        )
        stats = await run_pipeline(config)
        entries = []
        for path in changed_paths:
            metadata = changed_metadata[path]
            entries.append(
                FileManifestEntry(
                    file_path=path,
                    git_blob_id=metadata.git_blob_id,
                    git_entry_type=metadata.git_entry_type,
                    eligible=True,
                    eligibility_reason=metadata.eligibility_reason,
                    content_digest=metadata.content_digest,
                    chunk_digest=stats.chunk_digests[path],
                    chunk_count=stats.chunk_counts[path],
                )
            )
        return IndexProcessResult(
            entries=tuple(entries),
            embedded_chunks=stats.embedded_chunks,
        )

    runtime = IndexingRuntime(
        registry=context.registry,
        storage=context.storage,
        prove_source=prove,
        verify_source=verify_source_unchanged,
        check_embedding_readiness=context.provider.check_readiness,
        is_git_ancestor=ancestry,
        build_plan=build_plan,
        process_changed=process_changed,
    )
    return await runtime.execute(context.request)


def _git_common_dir(repo_root: Path) -> Path:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("Git common directory is unavailable")
    return Path(result.stdout.strip()).resolve(strict=True)
