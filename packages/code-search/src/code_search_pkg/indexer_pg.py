# pyright: reportMissingImports=false
"""CocoIndex source/chunk/embed adapter for isolated Postgres attempts.

This is deliberately the only module in ``code_search_pkg`` that imports the
heavy CocoIndex and ``cocoindex-code`` stacks. CocoIndex owns deterministic
source processing and memoized embedding; :mod:`storage_pg` owns every table
lifecycle operation.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

import cocoindex as coco
import numpy as np
from cocoindex.connectors import localfs
from cocoindex.ops.text import RecursiveSplitter, detect_code_language
from cocoindex.resources.chunk import Chunk
from cocoindex_code.chunking import CHUNKER_REGISTRY
from cocoindex_code.file_walk import build_matcher
from cocoindex_code.settings import load_project_settings
from cocoindex_code.shared import (
    CODEBASE_DIR,
    EMBEDDER,
    INDEXING_EMBED_PARAMS,
)

from .schema import CodeChunk, chunk_set_digest, stable_chunk_id
from .secret_scanner import LocalSecretScanner, SecretScanStatus
from .storage_pg import StorageAttempt, StoragePublisher

CHUNK_SIZE = 1000
MIN_CHUNK_SIZE = 250
CHUNK_OVERLAP = 150

_APP_PART = re.compile(r"[^a-zA-Z0-9_]+")
_splitter = RecursiveSplitter()

STORAGE_PUBLISHER = coco.ContextKey[StoragePublisher]("code_search_storage_publisher")
STORAGE_ATTEMPT = coco.ContextKey[StorageAttempt]("code_search_storage_attempt")
PIPELINE_FINGERPRINT = coco.ContextKey[str](
    "code_search_pipeline_fingerprint",
    detect_change=True,
)
CHANGED_PATHS = coco.ContextKey[tuple[str, ...]](
    "code_search_changed_paths",
    detect_change=True,
)


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """CocoIndex-visible chunk shape with an embedder-annotated vector."""

    file_path: str
    language: str
    content: str
    start_line: int
    end_line: int
    embedding: Annotated[np.ndarray[Any, Any], EMBEDDER]


@dataclass(slots=True)
class PipelineStats:
    """Measured changed-file output from one App update."""

    processed_files: int = 0
    embedded_chunks: int = 0
    chunk_counts: dict[str, int] = field(default_factory=dict)
    chunk_digests: dict[str, str] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def record(
        self,
        file_path: str,
        chunks: list[CodeChunk],
    ) -> None:
        async with self._lock:
            self.processed_files += 1
            self.embedded_chunks += len(chunks)
            self.chunk_counts[file_path] = len(chunks)
            self.chunk_digests[file_path] = chunk_set_digest(chunks)


PIPELINE_STATS = coco.ContextKey[PipelineStats]("code_search_pipeline_stats")
SECRET_SCANNER = coco.ContextKey[LocalSecretScanner]("code_search_local_secret_scanner")
EXPECTED_CONTENT_DIGESTS = coco.ContextKey[dict[str, str]](
    "code_search_expected_content_digests"
)


class ExactSourceMismatchError(RuntimeError):
    """The final source read did not match the exact planned Git blob."""


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Stable contexts required to construct one CocoIndex v1 App."""

    app_name: str
    cocoindex_state_path: Path
    repo_root: Path
    changed_paths: tuple[str, ...]
    expected_content_digests: Mapping[str, str]
    pipeline_fingerprint: str
    storage_publisher: StoragePublisher
    storage_attempt: StorageAttempt
    embedder: Any
    indexing_parameters: dict[str, Any]
    chunker_registry: Any = CHUNKER_REGISTRY
    secret_scanner: LocalSecretScanner = field(default_factory=LocalSecretScanner)

    def __post_init__(self) -> None:
        if not self.app_name:
            raise ValueError("app_name must not be empty")
        object.__setattr__(
            self,
            "cocoindex_state_path",
            Path(self.cocoindex_state_path).expanduser().resolve(strict=False),
        )
        object.__setattr__(
            self,
            "repo_root",
            Path(self.repo_root).expanduser().resolve(strict=True),
        )
        if len(self.pipeline_fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in self.pipeline_fingerprint
        ):
            raise ValueError("pipeline_fingerprint must be 64 lowercase hex characters")
        normalized = tuple(sorted(set(self.changed_paths)))
        for path in normalized:
            if (
                not path
                or path.startswith("/")
                or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                raise ValueError(
                    "changed_paths must be normalized repository-relative paths"
                )
        object.__setattr__(self, "changed_paths", normalized)
        digests = dict(self.expected_content_digests)
        if set(digests) != set(normalized):
            raise ValueError(
                "expected_content_digests must cover exactly the changed paths"
            )
        for digest in digests.values():
            if len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest
            ):
                raise ValueError(
                    "expected_content_digests must be 64 lowercase hex characters"
                )
        object.__setattr__(
            self,
            "expected_content_digests",
            dict(sorted(digests.items())),
        )


def stable_app_name(
    repo_slug: str,
    namespace_kind: str,
    namespace_key: str,
    pipeline_fingerprint: str,
) -> str:
    """Build a stable, non-secret App identity independent of attempt number."""

    identity = (
        f"code-search-app-v2\0{repo_slug}\0{namespace_kind}\0"
        f"{namespace_key}\0{pipeline_fingerprint}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    readable = _APP_PART.sub("_", f"{repo_slug}_{namespace_kind}").strip("_")
    return f"CodeSearch_{readable[:40]}_{digest}"


@coco.fn(memo=True)
async def build_file_chunks(
    file: localfs.File,
    expected_content_digest: str,
) -> list[EmbeddedChunk]:
    """Read, chunk, and embed one already-eligible changed file.

    Attempt-specific storage is intentionally absent from this memoized
    function's context. A retry may reuse chunk/embed computation while still
    writing into a fresh fenced staging table.
    """

    embedder = coco.use_context(EMBEDDER)
    indexing_params = coco.use_context(INDEXING_EMBED_PARAMS)

    try:
        content = await _read_exact_planned_text(file, expected_content_digest)
    except UnicodeDecodeError:
        return []
    if not content.strip():
        return []
    scan = coco.use_context(SECRET_SCANNER).scan_bytes(content.encode("utf-8"))
    if scan.status is SecretScanStatus.FINDING:
        raise RuntimeError(f"local secret scan rejected changed file ({scan.reason})")

    suffix = file.file_path.path.suffix
    project_root = coco.use_context(CODEBASE_DIR)
    settings = load_project_settings(project_root)
    extension_languages = {
        f".{override.ext}": override.lang for override in settings.language_overrides
    }
    language = (
        extension_languages.get(suffix)
        or detect_code_language(filename=file.file_path.path.name)
        or "text"
    )

    chunker = coco.use_context(CHUNKER_REGISTRY).get(suffix)
    if chunker is not None:
        language_override, chunks = chunker(Path(file.file_path.path), content)
        if language_override is not None:
            language = language_override
    else:
        chunks = _splitter.split(
            content,
            chunk_size=CHUNK_SIZE,
            min_chunk_size=MIN_CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            language=language,
        )

    async def embed_chunk(chunk: Chunk) -> EmbeddedChunk:
        return EmbeddedChunk(
            file_path=file.file_path.path.as_posix(),
            language=language,
            content=chunk.text,
            start_line=chunk.start.line,
            end_line=chunk.end.line,
            embedding=await embedder.embed(chunk.text, **indexing_params),
        )

    return await coco.map(embed_chunk, chunks)


async def _read_exact_planned_text(
    file: localfs.File,
    expected_content_digest: str,
) -> str:
    """Read once, verify exact Git bytes, then decode those same bytes."""

    content_bytes = await file.read()
    actual_digest = hashlib.sha256(content_bytes).hexdigest()
    if actual_digest != expected_content_digest:
        raise ExactSourceMismatchError(
            "changed source file no longer matches the planned Git blob"
        )
    return content_bytes.decode("utf-8", errors="strict")


@coco.fn
async def write_changed_file(file: localfs.File) -> None:
    """Materialize memoized chunks into this attempt's private table."""

    file_path = file.file_path.path.as_posix()
    expected_content_digest = coco.use_context(EXPECTED_CONTENT_DIGESTS).get(file_path)
    if expected_content_digest is None:
        raise ExactSourceMismatchError(
            "changed source file has no planned Git blob digest"
        )
    embedded = await build_file_chunks(file, expected_content_digest)
    pipeline_fingerprint = coco.use_context(PIPELINE_FINGERPRINT)
    chunks = [
        CodeChunk(
            id=stable_chunk_id(
                file_path=file_path,
                chunk_ordinal=ordinal,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                pipeline_fingerprint=pipeline_fingerprint,
            ),
            file_path=file_path,
            language=chunk.language,
            content=chunk.content,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            embedding=chunk.embedding,
        )
        for ordinal, chunk in enumerate(embedded)
    ]
    await coco.use_context(STORAGE_PUBLISHER).replace_file(
        coco.use_context(STORAGE_ATTEMPT),
        file_path,
        chunks,
    )
    await coco.use_context(PIPELINE_STATS).record(file_path, chunks)


@coco.fn
async def indexer_main() -> None:
    """Process only the exact paths selected by the light eligibility layer."""

    changed_paths = coco.use_context(CHANGED_PATHS)
    if not changed_paths:
        return
    project_root = coco.use_context(CODEBASE_DIR)
    matcher = build_matcher(project_root, list(changed_paths), [])
    files = localfs.walk_dir(
        CODEBASE_DIR,
        recursive=True,
        path_matcher=matcher,
    )
    await coco.mount_each(
        coco.component_subpath(coco.Symbol("write_changed_file")),
        write_changed_file,
        files.items(),
    )


def create_app(config: PipelineConfig, stats: PipelineStats) -> Any:
    """Construct the pinned CocoIndex v1 App with stable contexts."""

    context = coco.ContextProvider()
    context.provide(CODEBASE_DIR, config.repo_root)
    context.provide(EMBEDDER, config.embedder)
    context.provide(INDEXING_EMBED_PARAMS, config.indexing_parameters)
    context.provide(CHUNKER_REGISTRY, config.chunker_registry)
    context.provide(STORAGE_PUBLISHER, config.storage_publisher)
    context.provide(STORAGE_ATTEMPT, config.storage_attempt)
    context.provide(PIPELINE_FINGERPRINT, config.pipeline_fingerprint)
    context.provide(CHANGED_PATHS, config.changed_paths)
    context.provide(
        EXPECTED_CONTENT_DIGESTS,
        dict(config.expected_content_digests),
    )
    context.provide(PIPELINE_STATS, stats)
    context.provide(SECRET_SCANNER, config.secret_scanner)

    settings = coco.Settings.from_env(config.cocoindex_state_path)
    environment = coco.Environment(settings, context_provider=context)
    return coco.App(
        coco.AppConfig(name=config.app_name, environment=environment),
        indexer_main,
    )


async def run_pipeline(config: PipelineConfig) -> PipelineStats:
    """Run one CocoIndex update and return measured changed-file statistics."""

    stats = PipelineStats()
    app = create_app(config, stats)
    update = app.update()
    async for _snapshot in update.watch():
        pass
    return stats
