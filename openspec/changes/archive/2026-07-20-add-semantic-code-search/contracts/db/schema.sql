-- Database contract: add-semantic-code-search
-- Target: coordinator ParadeDB (Postgres + pgvector + pg_search)
--
-- Two object classes (design D6):
--   1. code_search_registry — coordinator-managed, applied as a normal additive migration.
--   2. code_chunks__<repo_slug> — REFERENCE SHAPE ONLY. These tables are created and evolved by
--      the vendored cocoindex pipeline (managed_by=SYSTEM target derived from the CodeChunk
--      dataclass). The DDL below documents the contracted shape the pipeline must produce; do
--      not apply it via the migration system.

-- ── 1. Coordinator-managed registry (migration: additive-only) ──────────────────────────────

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
    'Indexed-repo registry for semantic code search. embedder_model/embedding_dim pin the '
    'query-time embedder per repo (design D4: mismatch is a hard error).';

-- ── 2. Pipeline-managed chunk table (reference shape; one per repo) ─────────────────────────
-- Example for repo_slug = 'agentic_coding_tools'. Embedding dimension shown for
-- sentence-transformers all-MiniLM-L6-v2 (384); the actual dimension comes from
-- code_search_registry.embedding_dim for the repo.

-- CREATE TABLE code_chunks__agentic_coding_tools (
--     id         BIGINT       PRIMARY KEY,     -- content-derived id from cocoindex IdGenerator
--     file_path  TEXT         NOT NULL,        -- repo-root-relative, posix separators
--     language   TEXT         NOT NULL,        -- tree-sitter language id or 'text'
--     content    TEXT         NOT NULL,        -- chunk source text
--     start_line INTEGER      NOT NULL,
--     end_line   INTEGER      NOT NULL,
--     embedding  vector(384)  NOT NULL
-- );
--
-- Vector index declared by the pipeline (design D3):
-- CREATE INDEX code_chunks__agentic_coding_tools__vector__embedding
--     ON code_chunks__agentic_coding_tools
--     USING hnsw (embedding vector_cosine_ops);

-- Query contract (single-statement ranking + filtering; spec code-search
-- "Semantic Retrieval Query"):
--
-- SELECT file_path, language, content, start_line, end_line,
--        1 - (embedding <=> $1) AS score
-- FROM   code_chunks__<repo_slug>
-- WHERE  ($2::text[] IS NULL OR language = ANY($2))
--   AND  ($3::text[] IS NULL OR file_path LIKE ANY($3))
-- ORDER  BY embedding <=> $1
-- LIMIT  $4 OFFSET $5;
--
-- Phase 2 (design D3) adds a pg_search BM25 term fused via RRF inside the service; the table
-- and this contract's result columns are unchanged.
