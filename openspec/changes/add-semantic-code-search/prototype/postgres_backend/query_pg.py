"""PROTOTYPE — Postgres/pgvector read path for cocoindex-code (change: add-semantic-code-search).

Replaces ``cocoindex_code/query.py`` (147 lines). The upstream module needs three code paths
because sqlite-vec's vec0 KNN cannot combine nearest-neighbor with arbitrary filters:
per-partition KNN, a full-scan fallback for path filters, and a Python heapq merge across
language partitions. pgvector expresses ranking + filtering as ONE statement (spec code-search
"Semantic Retrieval Query"), so this module is ~60 lines and strictly simpler.

Phase 2 (design D3) adds a pg_search BM25 term fused via RRF here, behind the same signature.
NOT wired into any build — illustrative prototype.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from cocoindex_code.schema import QueryResult

from .indexer_pg import chunk_table_name

# Single-statement ranking + filtering (contracts/db/schema.sql query contract).
# `<=>` is pgvector cosine distance; score = 1 - distance maps to [0, 1] for unit vectors.
_SEARCH_SQL = """
SELECT file_path, language, content, start_line, end_line,
       1 - (embedding <=> $1) AS score
FROM   {table}
WHERE  ($2::text[] IS NULL OR language = ANY($2))
  AND  ($3::text[] IS NULL OR file_path LIKE ANY($3))
ORDER  BY embedding <=> $1
LIMIT  $4 OFFSET $5
"""


def _to_pgvector_literal(embedding: Any) -> str:
    """Encode a numpy vector in pgvector text format, e.g. '[0.1,0.2,...]'.

    Mirrors cocoindex.connectors.postgres._target._vector_encoder so query-time encoding is
    byte-compatible with what the indexer wrote.
    """
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


async def query_codebase_pg(
    pool: asyncpg.Pool,
    repo_slug: str,
    query_embedding: Any,
    *,
    limit: int = 10,
    offset: int = 0,
    languages: list[str] | None = None,
    paths: list[str] | None = None,
) -> list[QueryResult]:
    """Vector similarity search over one repo's chunk table.

    Embedding the query string is the caller's job (coordinator service, design D4 — it owns
    the registry consistency check between query-time and index-time embedder models).
    ``paths`` are SQL LIKE patterns (e.g. 'agent-coordinator/%'); scope-glob filtering (design
    D7) is applied by the service on top of these results.
    """
    table = chunk_table_name(repo_slug)  # validates the slug; table name is not user SQL
    rows = await pool.fetch(
        _SEARCH_SQL.format(table=table),
        _to_pgvector_literal(query_embedding),
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
