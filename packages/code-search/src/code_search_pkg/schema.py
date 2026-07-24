"""Row + result dataclasses for the Postgres backend.

Defined locally (not imported from cocoindex_code.schema) so the query path and the coordinator
service can depend on these types without pulling the heavy cocoindex/torch stack. The shapes
mirror upstream cocoindex-code (`CodeChunk`, `QueryResult`) so results stay drop-in compatible.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass
class CodeChunk:
    """One indexed chunk. `embedding` is the pgvector column (numpy array at index time).

    The `Annotated[..., EMBEDDER]` marker that cocoindex uses to derive the vector dimension is
    applied in indexer_pg.py, which owns the cocoindex import; this plain shape is what the query
    path and tests reason about.
    """

    id: str
    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    embedding: Any = (
        None  # NDArray[float32] at index time; not read back on the query path
    )


def stable_chunk_id(
    *,
    file_path: str,
    chunk_ordinal: int,
    start_line: int,
    end_line: int,
    content: str,
    pipeline_fingerprint: str,
) -> str:
    """Return a path-aware chunk identity stable within one pipeline contract."""
    if (
        not file_path
        or file_path.startswith("/")
        or "\\" in file_path
        or any(part in {"", ".", ".."} for part in file_path.split("/"))
    ):
        raise ValueError("file_path must be a normalized repository-relative path")
    if start_line < 1 or end_line < start_line:
        raise ValueError("chunk line range is invalid")
    if isinstance(chunk_ordinal, bool) or chunk_ordinal < 0:
        raise ValueError("chunk_ordinal must not be negative")
    if len(pipeline_fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in pipeline_fingerprint
    ):
        raise ValueError("pipeline_fingerprint must be 64 lowercase hex characters")
    digest = hashlib.sha256()
    for value in (
        "code-search-chunk-v2",
        pipeline_fingerprint,
        file_path,
        str(chunk_ordinal),
        str(start_line),
        str(end_line),
        hashlib.sha256(content.encode("utf-8")).hexdigest(),
    ):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def chunk_set_digest(chunks: Sequence[CodeChunk]) -> str:
    """Digest the ordered chunk identity/content set, including the empty set."""

    digest = hashlib.sha256()
    digest.update(b"code-search-chunk-set-v1\0")
    digest.update(str(len(chunks)).encode("ascii"))
    digest.update(b"\0")
    for chunk in chunks:
        for value in (
            str(chunk.id),
            chunk.file_path,
            str(chunk.start_line),
            str(chunk.end_line),
            hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
        ):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


@dataclass
class QueryResult:
    """One search hit. Mirrors cocoindex-code's QueryResult (score in [0, 1])."""

    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    score: float
