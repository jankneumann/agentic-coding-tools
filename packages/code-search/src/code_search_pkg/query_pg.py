"""Fail-closed Postgres/pgvector reads over immutable semantic-index storage."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from .identifiers import index_chunk_table_name, validate_slug, validate_storage_key
from .registry_models import IndexIdentity, LEGACY_FINGERPRINT, NamespaceKind
from .schema import QueryResult


_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_VECTOR_DIMENSION = 16_384
_MAX_LIMIT = 100
_MAX_OFFSET = 10_000
_MAX_LANGUAGES = 30
_MAX_LANGUAGE_LENGTH = 64
_MAX_ALLOW_PATH_REGEXES = 1
_MAX_DENY_PATH_REGEXES = 200
_MAX_CALLER_PATH_REGEXES = 100
# The authorization layer combines two 100-item SafeGlob allow layers into
# one lookahead expression. Escaping can double each 512-character glob, so
# 256 KiB safely contains the frozen worst case while remaining finite.
_MAX_COMPILED_ALLOW_REGEX_LENGTH = 256 * 1024
# Individual deny/caller globs remain separate after compilation. Twice the
# 512-character wire bound plus regex structure fits comfortably in 2 KiB.
_MAX_COMPILED_PATH_REGEX_LENGTH = 2 * 1024

# `<=>` is pgvector cosine distance. Cosine similarity is 1 - distance and its
# mathematical range is [-1, 1]; it is not a probability.
SEARCH_SQL = """
SELECT file_path, language, content, start_line, end_line,
       GREATEST(-1.0, LEAST(1.0, 1 - (embedding <=> $1))) AS score
FROM   {table}
WHERE  ($2::text[] IS NULL OR language = ANY($2))
  AND  ($3::text[] IS NULL OR file_path ~ ANY($3))
  AND  ($4::text[] IS NULL OR NOT (file_path ~ ANY($4)))
  AND  ($5::text[] IS NULL OR file_path ~ ANY($5))
ORDER  BY embedding <=> $1
LIMIT  $6 OFFSET $7
"""

_INDEX_PROJECTION = """
candidate.index_id,
candidate.storage_key,
candidate.repo_slug,
candidate.namespace_kind,
candidate.namespace_key,
candidate.source_revision,
candidate.embedder_model,
candidate.embedding_dim,
candidate.policy_fingerprint,
candidate.pipeline_fingerprint,
candidate.embedder_fingerprint,
candidate.chunk_count,
candidate.completed_at,
EXISTS (
    SELECT 1
    FROM code_search_index_files AS manifest
    WHERE manifest.index_id = candidate.index_id
) AS published_manifest,
to_regclass('code_chunks__' || candidate.storage_key) IS NOT NULL AS storage_exists
"""

SELECT_MAIN_INDEX_SQL = f"""
SELECT {_INDEX_PROJECTION}
FROM code_search_registry AS repository
JOIN code_search_indexes AS candidate
  ON repository.canonical_index_id = candidate.index_id
WHERE repository.repo_slug = $1
  AND candidate.repo_slug = repository.repo_slug
  AND candidate.namespace_kind = 'main'
  AND candidate.namespace_key = 'main'
  AND candidate.status = 'ready'
  AND candidate.policy_fingerprint <> repeat('0', 64)
  AND candidate.pipeline_fingerprint <> repeat('0', 64)
  AND candidate.embedder_fingerprint <> repeat('0', 64)
"""

SELECT_EXACT_INDEX_SQL = f"""
SELECT {_INDEX_PROJECTION}
FROM code_search_indexes AS candidate
WHERE candidate.index_id = $1
  AND candidate.repo_slug = $2
  AND candidate.namespace_kind = $3
  AND candidate.namespace_key = $4
  AND candidate.namespace_kind IN ('feature', 'work_package')
  AND candidate.status = 'ready'
  AND candidate.policy_fingerprint <> repeat('0', 64)
  AND candidate.pipeline_fingerprint <> repeat('0', 64)
  AND candidate.embedder_fingerprint <> repeat('0', 64)
"""


class SemanticStorageUnavailableError(RuntimeError):
    """The selected immutable table disappeared or cannot be addressed."""


class _Pool(Protocol):
    async def fetch(self, query: str, *args: Any) -> Sequence[Mapping[str, Any]]: ...

    async def fetchrow(
        self, query: str, *args: Any
    ) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class QueryProviderContract:
    """Non-secret provider identity that must match the indexed vectors."""

    model: str
    dimension: int
    embedder_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model:
            raise ValueError("model must not be empty")
        if (
            isinstance(self.dimension, bool)
            or not isinstance(self.dimension, int)
            or self.dimension <= 0
        ):
            raise ValueError("dimension must be a positive integer")
        if (
            not _FINGERPRINT_RE.fullmatch(self.embedder_fingerprint)
            or self.embedder_fingerprint == LEGACY_FINGERPRINT
        ):
            raise ValueError(
                "embedder_fingerprint must be a nonlegacy 64-character lowercase hex digest"
            )


@dataclass(frozen=True, slots=True)
class QueryableIndex:
    """Validated immutable index provenance returned by exact selectors."""

    index_id: UUID
    storage_key: str
    repo_slug: str
    namespace_kind: NamespaceKind
    namespace_key: str
    source_revision: str
    embedder_model: str
    embedding_dim: int
    policy_fingerprint: str
    pipeline_fingerprint: str
    embedder_fingerprint: str
    chunk_count: int
    completed_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> QueryableIndex:
        return cls(
            index_id=UUID(str(row["index_id"])),
            storage_key=str(row["storage_key"]),
            repo_slug=str(row["repo_slug"]),
            namespace_kind=NamespaceKind(str(row["namespace_kind"])),
            namespace_key=str(row["namespace_key"]),
            source_revision=str(row["source_revision"]),
            embedder_model=str(row["embedder_model"]),
            embedding_dim=int(row["embedding_dim"]),
            policy_fingerprint=str(row["policy_fingerprint"]),
            pipeline_fingerprint=str(row["pipeline_fingerprint"]),
            embedder_fingerprint=str(row["embedder_fingerprint"]),
            chunk_count=int(row["chunk_count"]),
            completed_at=row["completed_at"],
        )

    def __post_init__(self) -> None:
        validate_storage_key(self.storage_key)
        IndexIdentity(
            repo_slug=self.repo_slug,
            namespace_kind=self.namespace_kind,
            namespace_key=self.namespace_key,
            source_revision=self.source_revision,
            embedder_model=self.embedder_model,
            embedding_dim=self.embedding_dim,
            policy_fingerprint=self.policy_fingerprint,
            pipeline_fingerprint=self.pipeline_fingerprint,
            embedder_fingerprint=self.embedder_fingerprint,
        )
        if self.chunk_count <= 0:
            raise ValueError("queryable indexes require a positive chunk count")
        if (
            not isinstance(self.completed_at, datetime)
            or self.completed_at.tzinfo is None
        ):
            raise ValueError("queryable indexes require an aware completion timestamp")
        for name in (
            "policy_fingerprint",
            "pipeline_fingerprint",
            "embedder_fingerprint",
        ):
            value = getattr(self, name)
            if not _FINGERPRINT_RE.fullmatch(value) or value == LEGACY_FINGERPRINT:
                raise ValueError(f"{name} must be a nonlegacy fingerprint")

    def matches_provider(self, provider: QueryProviderContract) -> bool:
        return (
            self.embedder_model == provider.model
            and self.embedding_dim == provider.dimension
            and self.embedder_fingerprint == provider.embedder_fingerprint
        )


def to_pgvector_literal(embedding: Sequence[float]) -> str:
    """Encode one bounded finite vector in pgvector text format."""
    if not embedding or len(embedding) > _MAX_VECTOR_DIMENSION:
        raise ValueError("embedding dimension is outside the supported range")
    values: list[float] = []
    for value in embedding:
        if isinstance(value, bool):
            raise ValueError("embedding values must be finite numbers")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("embedding values must be finite numbers")
        values.append(number)
    return "[" + ",".join(repr(value) for value in values) + "]"


def build_search_sql(storage_key: str) -> str:
    """Build the one-statement KNN query from a validated immutable storage key."""
    validate_storage_key(storage_key)
    return SEARCH_SQL.format(table=index_chunk_table_name(storage_key))


async def select_main_index(pool: _Pool, repo_slug: str) -> QueryableIndex | None:
    """Select only the repository's guarded, ready canonical main index."""
    row = await pool.fetchrow(SELECT_MAIN_INDEX_SQL, validate_slug(repo_slug))
    return _decode_usable_index(row)


async def select_exact_index(
    pool: _Pool,
    *,
    index_id: UUID,
    repo_slug: str,
    namespace_kind: NamespaceKind | str,
    namespace_key: str,
) -> QueryableIndex | None:
    """Select one exact ready non-main index; never choose a fingerprint variant."""
    kind = NamespaceKind(namespace_kind)
    if kind is NamespaceKind.MAIN:
        raise ValueError("main selection must use select_main_index")
    if not namespace_key or len(namespace_key) > 255:
        raise ValueError("namespace_key must contain between 1 and 255 characters")
    row = await pool.fetchrow(
        SELECT_EXACT_INDEX_SQL,
        index_id,
        validate_slug(repo_slug),
        kind.value,
        namespace_key,
    )
    return _decode_usable_index(row)


def _decode_usable_index(row: Mapping[str, Any] | None) -> QueryableIndex | None:
    if (
        row is None
        or not row["published_manifest"]
        or not row["storage_exists"]
        or not row["chunk_count"]
    ):
        return None
    try:
        return QueryableIndex.from_row(row)
    except (KeyError, TypeError, ValueError):
        return None


async def query_codebase_pg(
    pool: _Pool,
    storage_key: str,
    query_embedding: Sequence[float],
    *,
    limit: int = 10,
    offset: int = 0,
    languages: list[str] | None = None,
    allow_path_regexes: list[str] | None = None,
    deny_path_regexes: list[str] | None = None,
    path_regexes: list[str] | None = None,
) -> list[QueryResult]:
    """Run one bounded, parameterized KNN statement over exact index storage."""
    _validate_pagination(limit, offset)
    _validate_filters(
        "languages", languages, _MAX_LANGUAGES, _MAX_LANGUAGE_LENGTH
    )
    _validate_filters(
        "allow_path_regexes",
        allow_path_regexes,
        _MAX_ALLOW_PATH_REGEXES,
        _MAX_COMPILED_ALLOW_REGEX_LENGTH,
    )
    _validate_filters(
        "deny_path_regexes",
        deny_path_regexes,
        _MAX_DENY_PATH_REGEXES,
        _MAX_COMPILED_PATH_REGEX_LENGTH,
    )
    _validate_filters(
        "path_regexes",
        path_regexes,
        _MAX_CALLER_PATH_REGEXES,
        _MAX_COMPILED_PATH_REGEX_LENGTH,
    )
    try:
        rows = await pool.fetch(
            build_search_sql(storage_key),
            to_pgvector_literal(query_embedding),
            languages,
            allow_path_regexes,
            deny_path_regexes,
            path_regexes,
            limit,
            offset,
        )
    except Exception as error:
        if getattr(error, "sqlstate", None) == "42P01":
            raise SemanticStorageUnavailableError(
                "semantic storage unavailable"
            ) from error
        raise
    return [
        QueryResult(
            file_path=str(row["file_path"]),
            language=str(row["language"]),
            content=str(row["content"]),
            start_line=int(row["start_line"]),
            end_line=int(row["end_line"]),
            score=float(row["score"]),
        )
        for row in rows
    ]


def _validate_pagination(limit: int, offset: int) -> None:
    if isinstance(limit, bool) or not 1 <= limit <= _MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
    if isinstance(offset, bool) or not 0 <= offset <= _MAX_OFFSET:
        raise ValueError(f"offset must be between 0 and {_MAX_OFFSET}")


def _validate_filters(
    name: str,
    values: list[str] | None,
    maximum_count: int,
    maximum_length: int,
) -> None:
    if values is None:
        return
    if len(values) > maximum_count:
        raise ValueError(f"{name} contains too many values")
    if any(
        not isinstance(value, str)
        or not value
        or len(value) > maximum_length
        or "\x00" in value
        for value in values
    ):
        raise ValueError(f"{name} contains an invalid value")
