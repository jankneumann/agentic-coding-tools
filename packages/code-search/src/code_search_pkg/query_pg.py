"""Postgres/pgvector read path (design D3).

Replaces cocoindex-code's sqlite-vec `query.py` (147 lines, three code paths) with a single
pgvector statement. Depends only on asyncpg (installable, no torch), so it is unit-testable with
a fake connection pool. Query-string embedding is the caller's job (coordinator service, D4).

Phase 2 (D3) adds a pg_search BM25 term fused via RRF; the signature and result columns here do
not change.
"""
from __future__ import annotations

from typing import Any, Protocol, Sequence

from .identifiers import chunk_table_name
from .schema import QueryResult

# `<=>` is pgvector cosine distance; score = 1 - distance ∈ [0, 1] for normalized embeddings.
# Both filters are applied in the same statement as the ORDER BY (spec: single-statement ranking).
SEARCH_SQL = """
SELECT file_path, language, content, start_line, end_line,
       1 - (embedding <=> $1) AS score
FROM   {table}
WHERE  ($2::text[] IS NULL OR language = ANY($2))
  AND  ($3::text[] IS NULL OR file_path LIKE ANY($3))
ORDER  BY embedding <=> $1
LIMIT  $4 OFFSET $5
"""


class _Fetcher(Protocol):
    """Minimal asyncpg.Pool surface used here — lets tests pass a fake."""

    async def fetch(self, query: str, *args: Any) -> Sequence[Any]: ...


def to_pgvector_literal(embedding: Sequence[float]) -> str:
    """Encode a vector in pgvector text format, e.g. '[0.1,0.2,0.3]'.

    Byte-compatible with cocoindex.connectors.postgres._target._vector_encoder, so query-time
    encoding matches what the indexer wrote.
    """
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def build_search_sql(repo_slug: str) -> str:
    """Return the search statement for a repo. Table name is slug-validated (not user SQL)."""
    return SEARCH_SQL.format(table=chunk_table_name(repo_slug))


async def query_codebase_pg(
    pool: _Fetcher,
    repo_slug: str,
    query_embedding: Sequence[float],
    *,
    limit: int = 10,
    offset: int = 0,
    languages: list[str] | None = None,
    paths: list[str] | None = None,
) -> list[QueryResult]:
    """Vector-similarity search over one repo's chunk table.

    `paths` are SQL LIKE patterns (e.g. 'agent-coordinator/%'). Scope-glob filtering (D7) is
    layered on top by the coordinator service; this function does only DB-side language/path
    filtering plus KNN ranking.
    """
    rows = await pool.fetch(
        build_search_sql(repo_slug),
        to_pgvector_literal(query_embedding),
        languages,
        paths,
        limit,
        offset,
    )
    return [
        QueryResult(
            file_path=r["file_path"],
            language=r["language"],
            content=r["content"],
            start_line=r["start_line"],
            end_line=r["end_line"],
            score=float(r["score"]),
        )
        for r in rows
    ]
