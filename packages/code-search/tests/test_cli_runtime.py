from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from code_search_pkg.cli import (
    RepositoryIdentityMismatch,
    _ensure_repository,
    _execute_operation,
)
from code_search_pkg.cli_runtime import resolve_cocoindex_state_path
from code_search_pkg.indexing_runtime import (
    IndexExecutionRequest,
    IndexExecutionStatus,
)
from code_search_pkg.registry_models import (
    IndexIdentity,
    IndexStatus,
    NamespaceKind,
    SemanticIndexRecord,
)

REVISION = "a" * 40
INDEX_ID = UUID("11111111-1111-4111-8111-111111111111")


class FakePool:
    def __init__(self) -> None:
        self.fetchrow_result: dict[str, object] | None = None
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.executions.append((query, args))
        return self.fetchrow_result


def test_cocoindex_state_is_durable_and_never_inside_source(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    common_dir = repo_root / ".git"
    external = tmp_path / "state"

    default_path = resolve_cocoindex_state_path(
        repo_root=repo_root,
        git_common_dir=common_dir,
        environment={},
        app_name="CodeSearch_example",
    )
    external_path = resolve_cocoindex_state_path(
        repo_root=repo_root,
        git_common_dir=common_dir,
        environment={"CODE_SEARCH_COCOINDEX_STATE_DIR": str(external)},
        app_name="CodeSearch_example",
    )

    assert default_path == common_dir / "code-search-cocoindex/CodeSearch_example"
    assert external_path == external / "CodeSearch_example"
    with pytest.raises(ValueError, match="outside the source worktree"):
        resolve_cocoindex_state_path(
            repo_root=repo_root,
            git_common_dir=common_dir,
            environment={"CODE_SEARCH_COCOINDEX_STATE_DIR": str(repo_root / ".state")},
            app_name="CodeSearch_example",
        )


@pytest.mark.asyncio
async def test_default_ready_no_op_does_not_import_cocoindex_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 23, tzinfo=UTC)
    identity = IndexIdentity(
        repo_slug="example",
        namespace_kind=NamespaceKind.MAIN,
        namespace_key="main",
        source_revision=REVISION,
        embedder_model="model",
        embedding_dim=3,
        policy_fingerprint="1" * 64,
        pipeline_fingerprint="2" * 64,
        embedder_fingerprint="3" * 64,
    )
    ready = SemanticIndexRecord(
        index_id=INDEX_ID,
        storage_key=f"i_{INDEX_ID.hex}",
        repo_slug="example",
        namespace_kind=NamespaceKind.MAIN,
        namespace_key="main",
        source_revision=REVISION,
        embedder_model="model",
        embedding_dim=3,
        status=IndexStatus.READY,
        attempt_count=1,
        chunk_count=2,
        last_error=None,
        lease_token=None,
        lease_owner=None,
        lease_expires_at=None,
        retention_until=None,
        started_at=now,
        completed_at=now,
        deleted_at=None,
        created_at=now,
        updated_at=now,
        policy_fingerprint="1" * 64,
        pipeline_fingerprint="2" * 64,
        embedder_fingerprint="3" * 64,
    )

    class ReadyRegistry:
        async def find_index(self, requested):
            assert requested == identity
            return ready

    class UnusedProvider:
        async def check_readiness(self):
            raise AssertionError("ready no-op must not check the provider")

    monkeypatch.setitem(sys.modules, "code_search_pkg.indexer_pg", None)
    context = SimpleNamespace(
        registry=ReadyRegistry(),
        storage=object(),
        provider=UnusedProvider(),
        repo_root=tmp_path,
        request=IndexExecutionRequest(
            identity=identity,
            repo_root=str(tmp_path),
            lease_owner="worker",
            lease_duration=timedelta(minutes=5),
        ),
    )

    ready_result = await _execute_operation(context)

    assert ready_result.status is IndexExecutionStatus.READY
    assert ready_result.reused is True


@pytest.mark.asyncio
async def test_repository_registration_preserves_explicit_contract(
    tmp_path: Path,
) -> None:
    pool = FakePool()
    pool.fetchrow_result = {
        "repo_slug": "example",
        "repo_root": str(tmp_path.resolve()),
        "git_common_dir_fingerprint": "f" * 64,
    }

    await _ensure_repository(
        pool,
        "example",
        tmp_path,
        "explicit-model",
        768,
        "f" * 64,
    )

    query, values = pool.executions[0]
    normalized_query = " ".join(query.split())
    assert "INSERT INTO code_search_registry" in query
    assert "ON CONFLICT (repo_slug)" in query
    assert "SET repo_root" not in query
    assert "THEN EXCLUDED.git_common_dir_fingerprint" in normalized_query
    assert values[:5] == (
        "example",
        str(tmp_path.resolve()),
        "f" * 64,
        "explicit-model",
        768,
    )


@pytest.mark.asyncio
async def test_repository_registration_rejects_slug_remapping(
    tmp_path: Path,
) -> None:
    pool = FakePool()

    with pytest.raises(RepositoryIdentityMismatch):
        await _ensure_repository(
            pool,
            "example",
            tmp_path,
            "explicit-model",
            768,
            "f" * 64,
        )
