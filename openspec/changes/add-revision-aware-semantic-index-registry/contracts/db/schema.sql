-- Contract: revision-aware semantic index registry.
-- Implementation target:
-- agent-coordinator/database/migrations/029_revision_aware_code_search_indexes.sql
--
-- This is additive. The existing code_search_registry table remains the
-- repository metadata and compatibility table.

CREATE TABLE code_search_indexes (
    index_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    storage_key        TEXT NOT NULL UNIQUE
                       CHECK (storage_key ~ '^i_[0-9a-f]{32}$'),
    repo_slug          TEXT NOT NULL
                       REFERENCES code_search_registry(repo_slug)
                       ON DELETE RESTRICT,
    namespace_kind     TEXT NOT NULL
                       CHECK (namespace_kind IN ('main', 'feature', 'work_package')),
    namespace_key      TEXT NOT NULL CHECK (length(namespace_key) BETWEEN 1 AND 255),
    source_revision    TEXT NOT NULL
                       CHECK (source_revision ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    embedder_model     TEXT NOT NULL CHECK (length(embedder_model) > 0),
    embedding_dim      INTEGER NOT NULL CHECK (embedding_dim > 0),
    status             TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN (
                           'pending', 'indexing', 'ready', 'failed',
                           'not_configured', 'deleting', 'deleted'
                       )),
    attempt_count      INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_token        UUID,
    lease_owner        TEXT,
    lease_expires_at   TIMESTAMPTZ,
    chunk_count        INTEGER CHECK (chunk_count >= 0),
    last_error         TEXT,
    retention_until    TIMESTAMPTZ,
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    deleted_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT code_search_indexes_main_key
        CHECK (namespace_kind <> 'main' OR namespace_key = 'main'),
    CONSTRAINT code_search_indexes_lease_shape
        CHECK (
            (status IN ('indexing', 'deleting')
             AND lease_token IS NOT NULL
             AND lease_owner IS NOT NULL
             AND lease_expires_at IS NOT NULL)
            OR
            (status NOT IN ('indexing', 'deleting')
             AND lease_token IS NULL
             AND lease_owner IS NULL
             AND lease_expires_at IS NULL)
        ),
    CONSTRAINT code_search_indexes_ready_shape
        CHECK (
            status <> 'ready'
            OR (chunk_count IS NOT NULL AND completed_at IS NOT NULL AND last_error IS NULL)
        ),
    CONSTRAINT code_search_indexes_deleted_shape
        CHECK (status <> 'deleted' OR deleted_at IS NOT NULL),
    CONSTRAINT code_search_indexes_natural_key UNIQUE (
        repo_slug,
        namespace_kind,
        namespace_key,
        source_revision,
        embedder_model,
        embedding_dim
    )
);

CREATE INDEX code_search_indexes_revision_lookup
    ON code_search_indexes (repo_slug, source_revision, status);

CREATE INDEX code_search_indexes_gc_candidates
    ON code_search_indexes (retention_until, status)
    WHERE namespace_kind IN ('feature', 'work_package');

ALTER TABLE code_search_registry
    ADD COLUMN canonical_index_id UUID;

ALTER TABLE code_search_registry
    ADD CONSTRAINT code_search_registry_canonical_index_fk
    FOREIGN KEY (canonical_index_id)
    REFERENCES code_search_indexes(index_id)
    ON DELETE RESTRICT;

-- The implementation migration defines a BEFORE INSERT OR UPDATE trigger on
-- code_search_indexes that fills storage_key as:
--
--   'i_' || replace(index_id::text, '-', '')
--
-- and DEFERRABLE constraint triggers on both code_search_registry and
-- code_search_indexes. They reject a canonical pointer, or a later mutation of
-- its target, unless the target row:
--   1. has the same repo_slug,
--   2. has namespace_kind = 'main', and
--   3. has status = 'ready'.
--
-- The Python registry additionally performs canonical promotion as one guarded
-- UPDATE with an expected_current_index_id compare-and-swap predicate.
