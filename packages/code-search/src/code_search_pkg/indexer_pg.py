"""Postgres/pgvector write path (design D1, D2, D3, D8).

Port of cocoindex-code's sqlite-vec `indexer.py` to `cocoindex.connectors.postgres`. Reuses the
upstream chunking / language-detection / file-walk / embedder modules as libraries — only the
storage mount and vector-index declaration change.

This module imports cocoindex (Rust engine) + cocoindex_code (upstream package), which pull the
embedding stack. It is therefore imported lazily by the CLI, never at package import time, so the
pure query/identifier logic stays testable without those heavy deps (design D8).
"""
from __future__ import annotations

import numpy as np  # noqa: F401  (kept for the Annotated embedding type below)

import cocoindex as coco
from cocoindex.connectors import localfs, postgres
from cocoindex.ops.text import RecursiveSplitter, detect_code_language
from cocoindex.resources.chunk import Chunk
from cocoindex.resources.id import IdGenerator

# Upstream modules reused unchanged (design D1/D8).
from cocoindex_code.chunking import CHUNKER_REGISTRY
from cocoindex_code.file_walk import build_matcher
from cocoindex_code.settings import load_project_settings
from cocoindex_code.shared import CODEBASE_DIR, EMBEDDER, INDEXING_EMBED_PARAMS

from .identifiers import chunk_table_name
from .schema import CodeChunk

# Upstream chunking configuration, unchanged.
CHUNK_SIZE = 1000
MIN_CHUNK_SIZE = 250
CHUNK_OVERLAP = 150

splitter = RecursiveSplitter()

# The asyncpg pool context key (replaces cocoindex-code's SQLITE_DB). Populated by the CLI from
# POSTGRES_DSN before the pipeline runs.
import asyncpg  # noqa: E402

PG_POOL = coco.ContextKey[asyncpg.Pool]("code_search_pg_pool")


@coco.fn(memo=True)
async def process_file(
    file: localfs.File,
    table: postgres.TableTarget[CodeChunk],
) -> None:
    """Chunk, embed, and store one file. Body matches upstream except the table type.

    ``memo=True`` is the incremental seam: memoization is framework-level, so only changed files
    re-run after the sqlite→postgres backend swap (decision-memo finding).
    """
    embedder = coco.use_context(EMBEDDER)
    indexing_params = coco.use_context(INDEXING_EMBED_PARAMS)

    try:
        content = await file.read_text()
    except UnicodeDecodeError:
        return
    if not content.strip():
        return

    suffix = file.file_path.path.suffix
    project_root = coco.use_context(CODEBASE_DIR)
    ps = load_project_settings(project_root)
    ext_lang_map = {f".{lo.ext}": lo.lang for lo in ps.language_overrides}
    language = (
        ext_lang_map.get(suffix)
        or detect_code_language(filename=file.file_path.path.name)
        or "text"
    )

    chunker = coco.use_context(CHUNKER_REGISTRY).get(suffix)
    if chunker is not None:
        language_override, chunks = chunker(file.file_path.path, content)
        if language_override is not None:
            language = language_override
    else:
        chunks = splitter.split(
            content,
            chunk_size=CHUNK_SIZE,
            min_chunk_size=MIN_CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            language=language,
        )

    id_gen = IdGenerator()

    async def process(chunk: Chunk) -> None:
        table.declare_row(
            row=CodeChunk(
                id=await id_gen.next_id(chunk.text),
                file_path=file.file_path.path.as_posix(),
                language=language,
                content=chunk.text,
                start_line=chunk.start.line,
                end_line=chunk.end.line,
                embedding=await embedder.embed(chunk.text, **indexing_params),
            )
        )

    await coco.map(process, chunks)


@coco.fn
async def indexer_main(repo_slug: str) -> None:
    """Walk files and process each — upstream flow with the Postgres mount swapped in."""
    project_root = coco.use_context(CODEBASE_DIR)
    ps = load_project_settings(project_root)

    table = await postgres.mount_table_target(
        db=PG_POOL,
        table_name=chunk_table_name(repo_slug),
        table_schema=await postgres.TableSchema.from_class(CodeChunk, primary_key=["id"]),
    )
    # Replaces sqlite-vec's Vec0TableDef: language/path filtering moves to the query statement;
    # only the HNSW cosine index is declared here (design D3).
    table.declare_vector_index(column="embedding", metric="cosine", method="hnsw")

    matcher = build_matcher(project_root, ps.include_patterns, ps.exclude_patterns)
    files = localfs.walk_dir(CODEBASE_DIR, recursive=True, path_matcher=matcher)

    await coco.mount_each(
        coco.component_subpath(coco.Symbol("process_file")),
        process_file,
        files.items(),
        table,
    )
