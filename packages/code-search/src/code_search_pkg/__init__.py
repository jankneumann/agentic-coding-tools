"""Vendored Postgres/pgvector backend for cocoindex-code (change: add-semantic-code-search).

Reuses ~95% of upstream cocoindex-code as a library and replaces only its two storage modules
(indexer.py / query.py) with pgvector equivalents (design D1).

Import layering (design D8):
  - identifiers, schema, query_pg  → light deps (asyncpg only); import-safe and unit-testable.
  - indexer_pg, cli                → pull cocoindex + the embedding stack; import lazily.

Importing this package does NOT import the heavy modules, so `from code_search_pkg import
chunk_table_name, query_codebase_pg` works without torch/cocoindex present.
"""
from __future__ import annotations

from .identifiers import chunk_table_name, slugify, validate_slug
from .query_pg import build_search_sql, query_codebase_pg, to_pgvector_literal
from .schema import CodeChunk, QueryResult

__all__ = [
    "chunk_table_name",
    "slugify",
    "validate_slug",
    "build_search_sql",
    "query_codebase_pg",
    "to_pgvector_literal",
    "CodeChunk",
    "QueryResult",
]
