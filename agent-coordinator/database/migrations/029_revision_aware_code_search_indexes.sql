-- Migration 029: revision-aware semantic index registry.
--
-- Additive successor to 028_code_search_registry.sql. The existing
-- code_search_registry table remains the compatibility/repository metadata
-- surface. This migration adds exact-revision index identities and one guarded
-- canonical pointer; it does not rename or remove any legacy column or chunk table.

CREATE TABLE IF NOT EXISTS code_search_indexes (
    index_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    storage_key        TEXT NOT NULL UNIQUE
                       CHECK (storage_key ~ '^i_[0-9a-f]{32}$'),
    repo_slug          TEXT NOT NULL
                       REFERENCES code_search_registry(repo_slug)
                       ON DELETE RESTRICT,
    namespace_kind     TEXT NOT NULL
                       CHECK (namespace_kind IN ('main', 'feature', 'work_package')),
    namespace_key      TEXT NOT NULL
                       CHECK (length(namespace_key) BETWEEN 1 AND 255),
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
            (
                status IN ('indexing', 'deleting')
                AND lease_token IS NOT NULL
                AND lease_owner IS NOT NULL
                AND lease_expires_at IS NOT NULL
            )
            OR
            (
                status NOT IN ('indexing', 'deleting')
                AND lease_token IS NULL
                AND lease_owner IS NULL
                AND lease_expires_at IS NULL
            )
        ),
    CONSTRAINT code_search_indexes_ready_shape
        CHECK (
            status <> 'ready'
            OR (
                chunk_count IS NOT NULL
                AND completed_at IS NOT NULL
                AND last_error IS NULL
            )
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

-- storage_key is derived exclusively from the durable UUID. Human-readable refs
-- and work-package names never become SQL identifiers.
CREATE OR REPLACE FUNCTION code_search_indexes_set_storage_key()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.storage_key := 'i_' || replace(NEW.index_id::text, '-', '');
    RETURN NEW;
END;
$function$;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'code_search_indexes_set_storage_key'
          AND tgrelid = 'code_search_indexes'::regclass
          AND NOT tgisinternal
    ) THEN
        EXECUTE
            'CREATE TRIGGER code_search_indexes_set_storage_key '
            'BEFORE INSERT OR UPDATE ON code_search_indexes '
            'FOR EACH ROW EXECUTE FUNCTION code_search_indexes_set_storage_key()';
    END IF;
END;
$migration$;

CREATE INDEX IF NOT EXISTS code_search_indexes_revision_lookup
    ON code_search_indexes (repo_slug, source_revision, status);

CREATE INDEX IF NOT EXISTS code_search_indexes_gc_candidates
    ON code_search_indexes (retention_until, status)
    WHERE namespace_kind IN ('feature', 'work_package');

ALTER TABLE code_search_registry
    ADD COLUMN IF NOT EXISTS canonical_index_id UUID;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'code_search_registry_canonical_index_fk'
          AND conrelid = 'code_search_registry'::regclass
    ) THEN
        EXECUTE
            'ALTER TABLE code_search_registry '
            'ADD CONSTRAINT code_search_registry_canonical_index_fk '
            'FOREIGN KEY (canonical_index_id) '
            'REFERENCES code_search_indexes(index_id) ON DELETE RESTRICT';
    END IF;
END;
$migration$;

-- Database-level defense for callers that bypass the registry library. The
-- application additionally uses row locking and compare-and-swap.
CREATE OR REPLACE FUNCTION code_search_registry_validate_canonical()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
DECLARE
    candidate code_search_indexes%ROWTYPE;
BEGIN
    IF NEW.canonical_index_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT *
    INTO candidate
    FROM code_search_indexes
    WHERE index_id = NEW.canonical_index_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'canonical semantic index % does not exist',
            NEW.canonical_index_id
            USING ERRCODE = '23514';
    END IF;

    IF candidate.repo_slug <> NEW.repo_slug
       OR candidate.namespace_kind <> 'main'
       OR candidate.status <> 'ready' THEN
        RAISE EXCEPTION
            'canonical semantic index must be a ready main index for repository %',
            NEW.repo_slug
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$function$;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'code_search_registry_validate_canonical'
          AND tgrelid = 'code_search_registry'::regclass
          AND NOT tgisinternal
    ) THEN
        EXECUTE
            'CREATE CONSTRAINT TRIGGER code_search_registry_validate_canonical '
            'AFTER INSERT OR UPDATE OF canonical_index_id ON code_search_registry '
            'DEFERRABLE INITIALLY IMMEDIATE '
            'FOR EACH ROW EXECUTE FUNCTION code_search_registry_validate_canonical()';
    END IF;
END;
$migration$;

COMMENT ON TABLE code_search_indexes IS
    'Authoritative revision-aware semantic-index lifecycle registry. '
    'One row identifies one repository/namespace/revision/embedder contract.';

COMMENT ON COLUMN code_search_registry.canonical_index_id IS
    'Ready main semantic index selected for this repository. Guarded by a '
    'same-repository/main/ready constraint trigger.';
