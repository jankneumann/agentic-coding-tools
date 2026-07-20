"""PROTOTYPE — Postgres/pgvector write path for cocoindex-code (change: add-semantic-code-search).

Port of ``cocoindex_code/indexer.py`` (123 lines, sqlite-vec) to the base framework's
``cocoindex.connectors.postgres`` target. Everything except the storage mount is reused from the
upstream package unchanged: chunker registry, language detection, file-walk matcher, settings,
embedder context keys.

Verified against source (2026-07-19):
  - cocoindex-code @ HEAD: src/cocoindex_code/indexer.py, shared.py
  - cocoindex @ HEAD: python/cocoindex/connectors/postgres/_target.py
      mount_table_target(db: ContextKey[asyncpg.Pool], table_name, table_schema, ...)
      TableSchema.from_class(cls, primary_key=[...])  (async; maps NDArray -> vector(n))
      TableTarget.declare_vector_index(column=..., metric="cosine", method="hnsw", ...)

Design decisions implemented: D2 (per-repo tables + slug validation), D3 (HNSW cosine),
D8 (upstream modules imported, not copied). NOT wired into any build — illustrative prototype.
"""

from __future__ import annotations

import re

import asyncpg
import cocoindex as coco
from cocoindex.connectors import localfs, postgres
from cocoindex.ops.text import RecursiveSplitter, detect_code_language
from cocoindex.resources.chunk import Chunk
from cocoindex.resources.id import IdGenerator

# Reused upstream modules (design D1/D8: libraries, not copies).
from cocoindex_code.chunking import CHUNKER_REGISTRY
from cocoindex_code.file_walk import build_matcher
from cocoindex_code.settings import load_project_settings
from cocoindex_code.shared import (
    CODEBASE_DIR,
    EMBEDDER,
    INDEXING_EMBED_PARAMS,
    CodeChunk,
)

# Upstream chunking configuration, unchanged.
CHUNK_SIZE = 1000
MIN_CHUNK_SIZE = 250
CHUNK_OVERLAP = 150

splitter = RecursiveSplitter()

# Replaces shared.SQLITE_DB: the connection context is an asyncpg pool pointed at the
# coordinator's ParadeDB (POSTGRES_DSN), created by the index_repo entrypoint.
PG_POOL = coco.ContextKey[asyncpg.Pool]("code_search_pg_pool")

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,50}$")


def chunk_table_name(repo_slug: str) -> str:
    """Per-repo chunk table (design D2). Slug is CHECK-constrained in the registry too."""
    if not _SLUG_RE.match(repo_slug):
        raise ValueError(f"invalid repo slug {repo_slug!r} (expected {_SLUG_RE.pattern})")
    return f"code_chunks__{repo_slug}"


@coco.fn(memo=True)
async def process_file(
    file: localfs.File,
    table: postgres.TableTarget[CodeChunk],
) -> None:
    """Chunk, embed, and store one file. Body identical to upstream except the table type.

    ``memo=True`` is the incremental-indexing seam: memoization lives in the framework, not the
    connector, so only changed files re-run after the backend swap (decision-memo finding).
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
        table_schema=await postgres.TableSchema.from_class(
            CodeChunk,
            primary_key=["id"],
        ),
    )
    # Replaces Vec0TableDef: partition/auxiliary columns are ordinary columns in Postgres;
    # language/path filtering moves into the query statement (query_pg.py).
    table.declare_vector_index(
        column="embedding",
        metric="cosine",
        method="hnsw",  # design D3; contracted index shape in contracts/db/schema.sql
    )

    matcher = build_matcher(project_root, ps.include_patterns, ps.exclude_patterns)
    files = localfs.walk_dir(CODEBASE_DIR, recursive=True, path_matcher=matcher)

    await coco.mount_each(
        coco.component_subpath(coco.Symbol("process_file")), process_file, files.items(), table
    )
