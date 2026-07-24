"""Resource-gated Postgres evidence for fail-closed v2 semantic search.

These tests execute migrations 028-030 and create/drop isolated registry rows
and chunk tables. Opt in only with a scratch database:

    CODE_SEARCH_V2_POSTGRES_DSN=postgresql://... \
    CODE_SEARCH_V2_ALLOW_SCRATCH_MUTATIONS=1 \
    uv run --project agent-coordinator pytest \
      agent-coordinator/tests/integration/postgres/test_code_search_v2.py -q

The query embedder is deterministic and local. No external embedding provider
is contacted; the resource gate covers Postgres/pgvector only.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from code_search_pkg.identifiers import index_chunk_table_name
from code_search_pkg.query_pg import QueryProviderContract

from src.code_search import (
    CodeSearchRequest,
    CodeSearchService,
    CodeSearchState,
)
from src.code_search_authorization import PrincipalCodeSearchGrant
from src.code_search_runtime import CodeSearchRuntime, CodeSearchRuntimeConfig

MIGRATIONS = Path(__file__).resolve().parents[3] / "database" / "migrations"
DSN = os.environ.get("CODE_SEARCH_V2_POSTGRES_DSN", "")
SCRATCH_MUTATIONS_ALLOWED = os.environ.get("CODE_SEARCH_V2_ALLOW_SCRATCH_MUTATIONS") == "1"
REVISION_A = "a" * 40
REVISION_B = "b" * 40
MODEL = "ri03-test-embedder"
DIMENSION = 3
POLICY_FINGERPRINT = "1" * 64
PIPELINE_FINGERPRINT = "2" * 64
EMBEDDER_FINGERPRINT = "3" * 64
PROVIDER = QueryProviderContract(
    model=MODEL,
    dimension=DIMENSION,
    embedder_fingerprint=EMBEDDER_FINGERPRINT,
)

pytestmark = pytest.mark.skipif(
    not DSN or not SCRATCH_MUTATIONS_ALLOWED,
    reason=(
        "resource-deferred: set CODE_SEARCH_V2_POSTGRES_DSN and "
        "CODE_SEARCH_V2_ALLOW_SCRATCH_MUTATIONS=1 for scratch Postgres evidence"
    ),
)


@dataclass(frozen=True, slots=True)
class PostgresCase:
    pool: asyncpg.Pool
    repo_slug: str
    dsn: str


@pytest.fixture(autouse=True)
async def cleanup_tables() -> AsyncIterator[None]:
    """Override the general coordinator cleanup for this isolated schema test."""

    yield


@pytest_asyncio.fixture
async def code_search_db() -> AsyncIterator[PostgresCase]:
    pool = await asyncpg.create_pool(dsn=DSN, min_size=1, max_size=2)
    repo_slug: str | None = None
    try:
        async with pool.acquire() as connection:
            for migration in (
                "028_code_search_registry.sql",
                "029_revision_aware_code_search_indexes.sql",
                "030_incremental_code_search_indexes.sql",
            ):
                await connection.execute((MIGRATIONS / migration).read_text(encoding="utf-8"))
            repo_slug = f"ri03_{uuid4().hex[:12]}"
            await connection.execute(
                """
                INSERT INTO code_search_registry (
                    repo_slug,
                    repo_root,
                    embedder_model,
                    embedding_dim,
                    git_common_dir_fingerprint
                )
                VALUES ($1, $2, $3, $4, $5)
                """,
                repo_slug,
                f"/scratch/{repo_slug}",
                MODEL,
                DIMENSION,
                "4" * 64,
            )
        case = PostgresCase(pool=pool, repo_slug=repo_slug, dsn=DSN)
        yield case
    finally:
        try:
            if repo_slug is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        "UPDATE code_search_registry "
                        "SET canonical_index_id = NULL WHERE repo_slug = $1",
                        repo_slug,
                    )
                    rows = await connection.fetch(
                        "SELECT storage_key FROM code_search_indexes WHERE repo_slug = $1",
                        repo_slug,
                    )
                    for row in rows:
                        table = index_chunk_table_name(str(row["storage_key"]))
                        await connection.execute(f"DROP TABLE IF EXISTS {table}")
                    await connection.execute(f"DROP TABLE IF EXISTS code_chunks__{repo_slug}")
                    await connection.execute(
                        "DELETE FROM code_search_indexes WHERE repo_slug = $1",
                        repo_slug,
                    )
                    await connection.execute(
                        "DELETE FROM code_search_registry WHERE repo_slug = $1",
                        repo_slug,
                    )
        finally:
            await pool.close()


async def _seed_ready_index(
    case: PostgresCase,
    *,
    revision: str,
    canonical: bool = True,
    create_storage: bool = True,
) -> tuple[UUID, str]:
    index_id = uuid4()
    async with case.pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            INSERT INTO code_search_indexes (
                index_id,
                repo_slug,
                namespace_kind,
                namespace_key,
                source_revision,
                embedder_model,
                embedding_dim,
                status,
                chunk_count,
                completed_at,
                policy_fingerprint,
                pipeline_fingerprint,
                embedder_fingerprint
            )
            VALUES (
                $1, $2, 'main', 'main', $3, $4, $5, 'ready', 1, now(),
                $6, $7, $8
            )
            RETURNING storage_key
            """,
            index_id,
            case.repo_slug,
            revision,
            MODEL,
            DIMENSION,
            POLICY_FINGERPRINT,
            PIPELINE_FINGERPRINT,
            EMBEDDER_FINGERPRINT,
        )
        assert row is not None
        storage_key = str(row["storage_key"])
        await connection.execute(
            """
            INSERT INTO code_search_index_files (
                index_id,
                file_path,
                git_blob_id,
                git_entry_type,
                eligible,
                eligibility_reason,
                content_digest,
                chunk_digest,
                chunk_count
            )
            VALUES (
                $1, 'src/service.py', $2, 'blob', true, 'eligible', $3, $4, 1
            )
            """,
            index_id,
            "5" * 40,
            "6" * 64,
            "7" * 64,
        )
        if create_storage:
            table = index_chunk_table_name(storage_key)
            await connection.execute(
                f"""
                CREATE TABLE {table} (
                    id text PRIMARY KEY,
                    file_path text NOT NULL,
                    language text NOT NULL,
                    content text NOT NULL,
                    start_line integer NOT NULL CHECK (start_line >= 1),
                    end_line integer NOT NULL CHECK (end_line >= start_line),
                    embedding vector({DIMENSION}) NOT NULL
                )
                """
            )
            await connection.execute(
                f"""
                INSERT INTO {table} (
                    id, file_path, language, content, start_line, end_line, embedding
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
                """,
                f"chunk-{index_id}",
                "src/service.py",
                "python",
                "def guarded_search(): return 'ready'",
                10,
                12,
                "[0.1,0.2,0.3]",
            )
        if canonical:
            await connection.execute(
                "UPDATE code_search_registry SET canonical_index_id = $2 WHERE repo_slug = $1",
                case.repo_slug,
                index_id,
            )
    return index_id, storage_key


def _request(case: PostgresCase, revision: str) -> CodeSearchRequest:
    return CodeSearchRequest.model_validate(
        {
            "query": "where is guarded search implemented",
            "repo_slug": case.repo_slug,
            "source_revision": revision,
            "namespace": {"kind": "main", "key": "main"},
            "scope": {
                "kind": "explicit",
                "read_allow": ["src/**"],
                "deny": ["src/private/**"],
            },
            "paths": ["src/**"],
        }
    )


def _service(
    case: PostgresCase,
    *,
    provider: QueryProviderContract = PROVIDER,
) -> tuple[CodeSearchService, dict[str, int]]:
    calls = {"embed": 0}

    async def embed(_query: str) -> list[float]:
        calls["embed"] += 1
        return [0.1, 0.2, 0.3]

    async def resolve_grant(
        principal_id: str,
        repo_slug: str,
    ) -> PrincipalCodeSearchGrant | None:
        return PrincipalCodeSearchGrant(
            principal_id=principal_id,
            repo_slug=repo_slug,
            namespace_kind="main",
            namespace_key="main",
            read_allow=("src/**",),
            deny=("src/private/**",),
        )

    return (
        CodeSearchService(
            pool=case.pool,
            embedder=embed,
            provider_contract=provider,
            grant_resolver=resolve_grant,
        ),
        calls,
    )


@pytest.mark.asyncio
async def test_exact_canonical_query_returns_v2_provenance_and_ready_status(
    code_search_db: PostgresCase,
) -> None:
    index_id, _storage_key = await _seed_ready_index(
        code_search_db,
        revision=REVISION_A,
    )
    service, calls = _service(code_search_db)

    response = await service.search(
        _request(code_search_db, REVISION_A),
        principal_id="integration-agent",
    )

    assert response.state is CodeSearchState.READY
    assert response.current is True
    assert response.fallback.required is False
    assert response.index is not None
    assert response.index.index_id == index_id
    assert response.index.source_revision == REVISION_A
    assert calls == {"embed": 1}
    assert [hit.file_path for hit in response.results] == ["src/service.py"]
    hit = response.results[0]
    assert hit.index_id == index_id
    assert hit.repo_slug == code_search_db.repo_slug
    assert hit.source_revision == REVISION_A
    assert hit.similarity == pytest.approx(1.0)

    class ReadyProvider:
        model_id = MODEL
        dimension = DIMENSION
        fingerprint = EMBEDDER_FINGERPRINT

        async def check_readiness(self) -> SimpleNamespace:
            return SimpleNamespace(state="ready")

    async def pool_factory() -> asyncpg.Pool:
        return await asyncpg.create_pool(dsn=code_search_db.dsn, min_size=1, max_size=1)

    runtime = await CodeSearchRuntime.create(
        CodeSearchRuntimeConfig(enabled=True),
        pool_factory=pool_factory,
        provider_factory=ReadyProvider,
        service_factory=lambda **_kwargs: object(),
    )
    try:
        status = await runtime.status()
    finally:
        await runtime.close()
    assert status.available is True
    assert status.state == "ready"
    assert status.reason == "ready"
    assert status.usable_index_count >= 1


@pytest.mark.asyncio
async def test_revision_mismatch_stops_before_embedding(
    code_search_db: PostgresCase,
) -> None:
    await _seed_ready_index(code_search_db, revision=REVISION_A)
    service, calls = _service(code_search_db)

    response = await service.search(
        _request(code_search_db, REVISION_B),
        principal_id="integration-agent",
    )

    assert response.state is CodeSearchState.REVISION_MISMATCH
    assert response.current is False
    assert response.results == []
    assert response.fallback.required is True
    assert response.fallback.reason is CodeSearchState.REVISION_MISMATCH
    assert calls == {"embed": 0}


@pytest.mark.asyncio
async def test_legacy_only_registry_and_repo_table_are_never_authoritative(
    code_search_db: PostgresCase,
) -> None:
    async with code_search_db.pool.acquire() as connection:
        await connection.execute(
            f"CREATE TABLE code_chunks__{code_search_db.repo_slug} (sentinel text NOT NULL)"
        )
        await connection.execute(
            f"INSERT INTO code_chunks__{code_search_db.repo_slug} VALUES ('legacy-hit')"
        )
    service, calls = _service(code_search_db)

    response = await service.search(
        _request(code_search_db, REVISION_A),
        principal_id="integration-agent",
    )

    assert response.state is CodeSearchState.NOT_INDEXED
    assert response.results == []
    assert response.index is None
    assert response.fallback.required is True
    assert calls == {"embed": 0}


@pytest.mark.asyncio
async def test_provider_mismatch_stops_before_embedding_and_storage(
    code_search_db: PostgresCase,
) -> None:
    await _seed_ready_index(code_search_db, revision=REVISION_A)
    mismatched_provider = QueryProviderContract(
        model="different-provider",
        dimension=DIMENSION,
        embedder_fingerprint=EMBEDDER_FINGERPRINT,
    )
    service, calls = _service(code_search_db, provider=mismatched_provider)

    response = await service.search(
        _request(code_search_db, REVISION_A),
        principal_id="integration-agent",
    )

    assert response.state is CodeSearchState.NOT_CONFIGURED
    assert response.results == []
    assert response.fallback.required is True
    assert response.fallback.reason is CodeSearchState.NOT_CONFIGURED
    assert calls == {"embed": 0}


@pytest.mark.asyncio
async def test_canonical_pointer_change_is_visible_without_stale_hits(
    code_search_db: PostgresCase,
) -> None:
    first_id, _first_storage = await _seed_ready_index(
        code_search_db,
        revision=REVISION_A,
    )
    second_id, _second_storage = await _seed_ready_index(
        code_search_db,
        revision=REVISION_B,
        canonical=False,
    )
    service, calls = _service(code_search_db)

    first = await service.search(
        _request(code_search_db, REVISION_A),
        principal_id="integration-agent",
    )
    async with code_search_db.pool.acquire() as connection:
        await connection.execute(
            "UPDATE code_search_registry SET canonical_index_id = $2 WHERE repo_slug = $1",
            code_search_db.repo_slug,
            second_id,
        )
    stale_request = await service.search(
        _request(code_search_db, REVISION_A),
        principal_id="integration-agent",
    )
    second = await service.search(
        _request(code_search_db, REVISION_B),
        principal_id="integration-agent",
    )

    assert first.state is CodeSearchState.READY
    assert first.index is not None and first.index.index_id == first_id
    assert stale_request.state is CodeSearchState.REVISION_MISMATCH
    assert stale_request.results == []
    assert stale_request.index is not None
    assert stale_request.index.index_id == second_id
    assert second.state is CodeSearchState.READY
    assert second.index is not None and second.index.index_id == second_id
    assert calls == {"embed": 2}


@pytest.mark.asyncio
async def test_missing_final_table_is_unavailable_without_semantic_work(
    code_search_db: PostgresCase,
) -> None:
    await _seed_ready_index(
        code_search_db,
        revision=REVISION_A,
        create_storage=False,
    )
    service, calls = _service(code_search_db)

    response = await service.search(
        _request(code_search_db, REVISION_A),
        principal_id="integration-agent",
    )

    assert response.state is CodeSearchState.UNAVAILABLE
    assert response.current is False
    assert response.results == []
    assert response.fallback.required is True
    assert response.fallback.reason is CodeSearchState.UNAVAILABLE
    assert calls == {"embed": 0}
