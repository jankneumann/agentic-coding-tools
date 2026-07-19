-- Migration: code_search_registry for semantic code search (change: add-semantic-code-search).
--
-- Additive-only (design D10 / D6). Creates the registry that tracks which repos are indexed and
-- with which embedder. Per-repo chunk tables (code_chunks__<slug>) are NOT created here — they
-- are system-managed by the cocoindex pipeline (packages/code-search/indexer_pg.py), which
-- derives their schema from the CodeChunk dataclass. This migration owns only the registry.
--
-- Matches openspec/changes/add-semantic-code-search/contracts/db/schema.sql. The pgvector
-- extension is ensured here so the pipeline can declare vector(n) columns + HNSW indexes.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS code_search_registry (
    repo_slug           TEXT PRIMARY KEY
                        CHECK (repo_slug ~ '^[a-z][a-z0-9_]{0,50}$'),
    repo_root           TEXT        NOT NULL,
    last_indexed_commit TEXT,
    embedder_model      TEXT        NOT NULL,
    embedding_dim       INTEGER     NOT NULL CHECK (embedding_dim > 0),
    chunk_count         INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE code_search_registry IS
    'Indexed-repo registry for semantic code search (add-semantic-code-search). '
    'embedder_model/embedding_dim pin the query-time embedder per repo — a mismatch is a hard '
    'error, never a silently degraded search (design D4).';
