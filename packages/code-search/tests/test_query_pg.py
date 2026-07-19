"""Unit tests for the pgvector read path (design D3). Uses a fake pool — no live DB needed."""
from __future__ import annotations

import pytest

from code_search_pkg.query_pg import (
    build_search_sql,
    query_codebase_pg,
    to_pgvector_literal,
)


def test_pgvector_literal_roundtrip_shape():
    assert to_pgvector_literal([0.1, 0.2, -0.3]).startswith("[")
    assert to_pgvector_literal([1.0, 2.0]) == "[1.0,2.0]"


def test_build_search_sql_targets_per_repo_table():
    sql = build_search_sql("agentic_coding_tools")
    assert "code_chunks__agentic_coding_tools" in sql
    # Single-statement: ranking + both filters live in one SELECT (spec code-search.5).
    assert sql.count("SELECT") == 1
    assert "embedding <=> $1" in sql            # cosine KNN
    assert "language = ANY($2)" in sql          # language filter
    assert "file_path LIKE ANY($3)" in sql      # path filter


def test_build_search_sql_rejects_bad_slug():
    with pytest.raises(ValueError):
        build_search_sql("Bad Slug")


class _FakePool:
    """Records the fetch() call and returns canned rows."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self._rows


@pytest.mark.asyncio
async def test_query_codebase_maps_rows_and_binds_params():
    rows = [
        {
            "file_path": "agent-coordinator/src/locks.py",
            "language": "python",
            "content": "def release(): ...",
            "start_line": 10,
            "end_line": 20,
            "score": 0.83,
        }
    ]
    pool = _FakePool(rows)
    results = await query_codebase_pg(
        pool,
        "agentic_coding_tools",
        [0.1, 0.2, 0.3],
        limit=5,
        offset=2,
        languages=["python"],
        paths=["agent-coordinator/%"],
    )
    assert len(results) == 1
    r = results[0]
    assert r.file_path == "agent-coordinator/src/locks.py"
    assert r.score == pytest.approx(0.83)

    # Parameter binding order matches the SQL placeholders $1..$5.
    _query, args = pool.calls[0]
    embedding_literal, languages, paths, limit, offset = args
    assert embedding_literal == "[0.1,0.2,0.3]"
    assert languages == ["python"]
    assert paths == ["agent-coordinator/%"]
    assert (limit, offset) == (5, 2)


@pytest.mark.asyncio
async def test_query_codebase_passes_none_filters_through():
    pool = _FakePool([])
    await query_codebase_pg(pool, "repo1", [0.0])
    _query, args = pool.calls[0]
    assert args[1] is None and args[2] is None  # languages, paths default to NULL
