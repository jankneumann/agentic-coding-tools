"""Row + result dataclasses for the Postgres backend.

Defined locally (not imported from cocoindex_code.schema) so the query path and the coordinator
service can depend on these types without pulling the heavy cocoindex/torch stack. The shapes
mirror upstream cocoindex-code (`CodeChunk`, `QueryResult`) so results stay drop-in compatible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CodeChunk:
    """One indexed chunk. `embedding` is the pgvector column (numpy array at index time).

    The `Annotated[..., EMBEDDER]` marker that cocoindex uses to derive the vector dimension is
    applied in indexer_pg.py, which owns the cocoindex import; this plain shape is what the query
    path and tests reason about.
    """

    id: int
    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    embedding: Any = None  # NDArray[float32] at index time; not read back on the query path


@dataclass
class QueryResult:
    """One search hit. Mirrors cocoindex-code's QueryResult (score in [0, 1])."""

    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    score: float
