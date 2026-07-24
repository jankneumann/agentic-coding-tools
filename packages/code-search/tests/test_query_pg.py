"""Unit tests for exact-index pgvector reads (design D2/D3/D7)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import UUID

import pytest

from code_search_pkg.query_pg import (
    QueryProviderContract,
    QueryableIndex,
    build_search_sql,
    query_codebase_pg,
    select_exact_index,
    select_main_index,
    to_pgvector_literal,
)


STORAGE_KEY = "i_11111111111141118111111111111111"
INDEX_ID = UUID("11111111-1111-4111-8111-111111111111")


def test_pgvector_literal_roundtrip_shape() -> None:
    assert to_pgvector_literal([0.1, 0.2, -0.3]) == "[0.1,0.2,-0.3]"


@pytest.mark.parametrize("value", [[], [math.nan], [math.inf], [True]])
def test_pgvector_literal_rejects_invalid_vectors(value: list[object]) -> None:
    with pytest.raises(ValueError):
        to_pgvector_literal(value)  # type: ignore[arg-type]


def test_build_search_sql_targets_validated_storage_key() -> None:
    sql = build_search_sql(STORAGE_KEY)
    assert "code_chunks__i_11111111111141118111111111111111" in sql
    assert "code_chunks__agentic_coding_tools" not in sql
    assert sql.count("SELECT") == 1
    assert "embedding <=> $1" in sql
    assert "language = ANY($2)" in sql
    assert "file_path ~ ANY($3)" in sql
    assert "NOT (file_path ~ ANY($4))" in sql
    assert "file_path ~ ANY($5)" in sql


@pytest.mark.parametrize("key", ["agentic_coding_tools", "i_bad", "i_" + "a" * 31])
def test_build_search_sql_rejects_non_storage_keys(key: str) -> None:
    with pytest.raises(ValueError):
        build_search_sql(key)


class _FakePool:
    def __init__(self, *, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.calls.append((query, args))
        return self.rows

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.calls.append((query, args))
        return self.rows[0] if self.rows else None


def _index_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "index_id": INDEX_ID,
        "storage_key": STORAGE_KEY,
        "repo_slug": "agentic_coding_tools",
        "namespace_kind": "main",
        "namespace_key": "main",
        "source_revision": "a" * 40,
        "embedder_model": "nomic-embed-text",
        "embedding_dim": 768,
        "policy_fingerprint": "1" * 64,
        "pipeline_fingerprint": "2" * 64,
        "embedder_fingerprint": "3" * 64,
        "chunk_count": 3,
        "completed_at": datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
        "published_manifest": True,
        "storage_exists": True,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_main_selector_joins_guarded_canonical_ready_index() -> None:
    pool = _FakePool(rows=[_index_row()])
    selected = await select_main_index(pool, "agentic_coding_tools")
    assert selected is not None
    assert selected.index_id == INDEX_ID
    assert selected.completed_at == datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    sql, args = pool.calls[0]
    assert "canonical_index_id = candidate.index_id" in sql
    assert "candidate.namespace_kind = 'main'" in sql
    assert "candidate.status = 'ready'" in sql
    assert "repeat('0', 64)" in sql
    assert "'code_chunks__' || candidate.storage_key" in sql
    assert "'code_chunks__' || repository.repo_slug" not in sql
    assert args == ("agentic_coding_tools",)


@pytest.mark.asyncio
async def test_non_main_selector_uses_exact_id_and_identity() -> None:
    pool = _FakePool(rows=[_index_row(namespace_kind="feature", namespace_key="ri03")])
    selected = await select_exact_index(
        pool,
        index_id=INDEX_ID,
        repo_slug="agentic_coding_tools",
        namespace_kind="feature",
        namespace_key="ri03",
    )
    assert selected is not None
    sql, args = pool.calls[0]
    assert "candidate.index_id = $1" in sql
    assert "candidate.repo_slug = $2" in sql
    assert "candidate.namespace_kind = $3" in sql
    assert "candidate.namespace_key = $4" in sql
    assert "ORDER BY" not in sql
    assert args == (INDEX_ID, "agentic_coding_tools", "feature", "ri03")


@pytest.mark.asyncio
async def test_selectors_reject_unpublished_or_incomplete_indexes() -> None:
    for override in (
        {"published_manifest": False},
        {"chunk_count": 0},
        {"completed_at": None},
    ):
        pool = _FakePool(rows=[_index_row(**override)])
        selected = await select_main_index(pool, "agentic_coding_tools")
        assert selected is None


@pytest.mark.asyncio
async def test_selector_reports_disappeared_final_storage_as_unavailable() -> None:
    from code_search_pkg.query_pg import SemanticStorageUnavailableError

    pool = _FakePool(rows=[_index_row(storage_exists=False)])
    with pytest.raises(
        SemanticStorageUnavailableError, match="semantic storage unavailable"
    ):
        await select_main_index(pool, "agentic_coding_tools")


def test_selected_index_requires_complete_provider_match() -> None:
    index = QueryableIndex.from_row(_index_row())
    assert index.matches_provider(
        QueryProviderContract("nomic-embed-text", 768, "3" * 64)
    )
    assert not index.matches_provider(
        QueryProviderContract("nomic-embed-text", 768, "4" * 64)
    )


@pytest.mark.asyncio
async def test_query_codebase_maps_rows_and_binds_bounded_scope_filters() -> None:
    pool = _FakePool(
        rows=[
            {
                "file_path": "agent-coordinator/src/locks.py",
                "language": "python",
                "content": "def release(): ...",
                "start_line": 10,
                "end_line": 20,
                "score": -0.25,
            }
        ]
    )
    results = await query_codebase_pg(
        pool,
        STORAGE_KEY,
        [0.1, 0.2, 0.3],
        limit=5,
        offset=2,
        languages=["python"],
        allow_path_regexes=[r"^agent-coordinator/.*$"],
        deny_path_regexes=[r"^agent-coordinator/secrets/.*$"],
        path_regexes=[r"^agent-coordinator/src/.*$"],
    )
    assert results[0].score == pytest.approx(-0.25)
    _query, args = pool.calls[0]
    assert args == (
        "[0.1,0.2,0.3]",
        ["python"],
        [r"^agent-coordinator/.*$"],
        [r"^agent-coordinator/secrets/.*$"],
        [r"^agent-coordinator/src/.*$"],
        5,
        2,
    )


@pytest.mark.asyncio
async def test_query_accepts_frozen_contract_scope_boundaries() -> None:
    pool = _FakePool()
    # Two 100-glob allow layers are compiled by the authorization service into
    # one lookahead regex. At the 512-character SafeGlob wire bound that
    # expression can be over 200 KiB after escaping and union construction.
    compiled_allow = "^" + "(?=" + ("a" * 205_000) + ").*$"
    authority_and_caller_denies = [rf"^deny-{index}/.*$" for index in range(200)]
    caller_paths = [rf"^path-{index}/.*$" for index in range(100)]

    await query_codebase_pg(
        pool,
        STORAGE_KEY,
        [0.1],
        allow_path_regexes=[compiled_allow],
        deny_path_regexes=authority_and_caller_denies,
        path_regexes=caller_paths,
    )

    assert pool.calls[0][1][2] == [compiled_allow]
    assert pool.calls[0][1][3] == authority_and_caller_denies
    assert pool.calls[0][1][4] == caller_paths


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"offset": -1}, "offset"),
        ({"offset": 10_001}, "offset"),
        ({"languages": ["python"] * 33}, "languages"),
        ({"allow_path_regexes": ["^x$", "^y$"]}, "allow_path_regexes"),
        ({"allow_path_regexes": ["x" * 262_145]}, "allow_path_regexes"),
        ({"deny_path_regexes": ["^x$"] * 201}, "deny_path_regexes"),
        ({"deny_path_regexes": ["x" * 2_049]}, "deny_path_regexes"),
        ({"path_regexes": ["^x$"] * 101}, "path_regexes"),
        ({"path_regexes": ["x" * 2_049]}, "path_regexes"),
    ],
)
async def test_query_rejects_unbounded_inputs(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        await query_codebase_pg(
            _FakePool(),
            STORAGE_KEY,
            [0.1],
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_query_has_no_legacy_fallback_on_missing_storage() -> None:
    class UndefinedTableError(RuntimeError):
        sqlstate = "42P01"

    class MissingStoragePool(_FakePool):
        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            self.calls.append((query, args))
            raise UndefinedTableError

    pool = MissingStoragePool()
    from code_search_pkg.query_pg import SemanticStorageUnavailableError

    with pytest.raises(
        SemanticStorageUnavailableError, match="semantic storage unavailable"
    ):
        await query_codebase_pg(pool, STORAGE_KEY, [0.1])
    assert len(pool.calls) == 1
    assert "code_chunks__i_" in pool.calls[0][0]
