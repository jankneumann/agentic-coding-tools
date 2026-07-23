-- Contract delta implemented by migration 030_incremental_code_search_indexes.sql.
-- Migration 029 must already have created code_search_indexes.

ALTER TABLE code_search_registry
    ADD COLUMN git_common_dir_fingerprint text NULL;

-- Existing repository rows are upgraded in place on their first proven
-- indexing request. New registrations must never use this legacy sentinel.
UPDATE code_search_registry
SET git_common_dir_fingerprint = repeat('0', 64)
WHERE git_common_dir_fingerprint IS NULL;

ALTER TABLE code_search_registry
    ALTER COLUMN git_common_dir_fingerprint SET NOT NULL,
    ADD CONSTRAINT code_search_registry_git_common_dir_fingerprint_ck
        CHECK (git_common_dir_fingerprint ~ '^[0-9a-f]{64}$');

-- Repository slugs cannot be rebound. A same-root legacy row may upgrade its
-- zero fingerprint once; a real fingerprint and the canonical root are then
-- immutable.
CREATE FUNCTION validate_code_search_repository_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.repo_root IS DISTINCT FROM OLD.repo_root THEN
        RAISE EXCEPTION 'code-search repository root is immutable';
    END IF;
    IF NEW.git_common_dir_fingerprint IS DISTINCT FROM
       OLD.git_common_dir_fingerprint
       AND OLD.git_common_dir_fingerprint <> repeat('0', 64) THEN
        RAISE EXCEPTION 'code-search Git common-directory identity is immutable';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER code_search_registry_identity_guard
BEFORE UPDATE OF repo_root, git_common_dir_fingerprint
ON code_search_registry
FOR EACH ROW EXECUTE FUNCTION validate_code_search_repository_identity();

ALTER TABLE code_search_indexes
    ADD COLUMN policy_fingerprint text NULL,
    ADD COLUMN pipeline_fingerprint text NULL,
    ADD COLUMN embedder_fingerprint text NULL,
    ADD COLUMN parent_index_id uuid NULL
        REFERENCES code_search_indexes(index_id) ON DELETE RESTRICT;

-- Existing ri-01 rows predate computation fingerprints. They receive an
-- explicit legacy sentinel which compatible-parent lookup must exclude.
UPDATE code_search_indexes
SET policy_fingerprint = repeat('0', 64),
    pipeline_fingerprint = repeat('0', 64),
    embedder_fingerprint = repeat('0', 64)
WHERE policy_fingerprint IS NULL
   OR pipeline_fingerprint IS NULL
   OR embedder_fingerprint IS NULL;

ALTER TABLE code_search_indexes
    ALTER COLUMN policy_fingerprint SET NOT NULL,
    ALTER COLUMN pipeline_fingerprint SET NOT NULL,
    ALTER COLUMN embedder_fingerprint SET NOT NULL;

ALTER TABLE code_search_indexes
    ADD CONSTRAINT code_search_indexes_policy_fingerprint_ck
        CHECK (policy_fingerprint ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT code_search_indexes_pipeline_fingerprint_ck
        CHECK (pipeline_fingerprint ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT code_search_indexes_embedder_fingerprint_ck
        CHECK (embedder_fingerprint ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT code_search_indexes_parent_not_self_ck
        CHECK (parent_index_id IS NULL OR parent_index_id <> index_id);

ALTER TABLE code_search_indexes
    DROP CONSTRAINT code_search_indexes_natural_key;

ALTER TABLE code_search_indexes
    ADD CONSTRAINT code_search_indexes_natural_key UNIQUE (
        repo_slug,
        namespace_kind,
        namespace_key,
        source_revision,
        embedder_model,
        embedding_dim,
        policy_fingerprint,
        pipeline_fingerprint,
        embedder_fingerprint
    );

CREATE INDEX code_search_indexes_compatible_parent_idx
    ON code_search_indexes (
        repo_slug,
        namespace_kind,
        namespace_key,
        embedder_model,
        embedding_dim,
        policy_fingerprint,
        pipeline_fingerprint,
        embedder_fingerprint,
        completed_at DESC
    )
    WHERE status = 'ready';

-- Attempt manifests isolate stale workers. They are never consumed by readers.
CREATE TABLE code_search_index_file_attempts (
    index_id uuid NOT NULL
        REFERENCES code_search_indexes(index_id) ON DELETE CASCADE,
    attempt_count integer NOT NULL CHECK (attempt_count > 0),
    file_path text NOT NULL,
    git_blob_id text NULL,
    git_entry_type text NULL CHECK (
        git_entry_type IS NULL OR git_entry_type IN ('blob', 'symlink')
    ),
    eligible boolean NOT NULL,
    eligibility_reason text NOT NULL,
    content_digest text NULL,
    chunk_digest text NULL,
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    PRIMARY KEY (index_id, attempt_count, file_path),
    CHECK (
        file_path <> ''
        AND file_path !~ '(^|/)\.\.(/|$)'
        AND file_path !~ '^/'
        AND file_path !~ '\\'
    ),
    CHECK (git_blob_id IS NULL OR git_blob_id ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    CHECK (content_digest IS NULL OR content_digest ~ '^[0-9a-f]{64}$'),
    CHECK (chunk_digest IS NULL OR chunk_digest ~ '^[0-9a-f]{64}$'),
    CHECK (
        (
            eligible
            AND git_blob_id IS NOT NULL
            AND git_entry_type IS NOT NULL
            AND content_digest IS NOT NULL
            AND chunk_digest IS NOT NULL
        )
        OR
        (NOT eligible AND chunk_count = 0)
    )
);

-- Published manifests are populated only by the fenced publish transaction.
CREATE TABLE code_search_index_files (
    index_id uuid NOT NULL
        REFERENCES code_search_indexes(index_id) ON DELETE CASCADE,
    file_path text NOT NULL,
    git_blob_id text NULL,
    git_entry_type text NULL CHECK (
        git_entry_type IS NULL OR git_entry_type IN ('blob', 'symlink')
    ),
    eligible boolean NOT NULL,
    eligibility_reason text NOT NULL,
    content_digest text NULL,
    chunk_digest text NULL,
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    PRIMARY KEY (index_id, file_path),
    CHECK (
        file_path <> ''
        AND file_path !~ '(^|/)\.\.(/|$)'
        AND file_path !~ '^/'
        AND file_path !~ '\\'
    ),
    CHECK (git_blob_id IS NULL OR git_blob_id ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
    CHECK (content_digest IS NULL OR content_digest ~ '^[0-9a-f]{64}$'),
    CHECK (chunk_digest IS NULL OR chunk_digest ~ '^[0-9a-f]{64}$'),
    CHECK (
        (
            eligible
            AND git_blob_id IS NOT NULL
            AND git_entry_type IS NOT NULL
            AND content_digest IS NOT NULL
            AND chunk_digest IS NOT NULL
        )
        OR
        (NOT eligible AND chunk_count = 0)
    )
);

CREATE INDEX code_search_index_files_blob_idx
    ON code_search_index_files (index_id, git_blob_id)
    WHERE eligible;

-- Parent linkage guard. Git ancestry remains an application check because the
-- database does not contain the Git object graph.
CREATE FUNCTION validate_code_search_parent() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    candidate code_search_indexes%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.status = 'ready'
       AND NEW.parent_index_id IS DISTINCT FROM OLD.parent_index_id THEN
        RAISE EXCEPTION 'ready index parent is immutable'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.parent_index_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT * INTO candidate
    FROM code_search_indexes
    WHERE index_id = NEW.parent_index_id
      AND status = 'ready'
    FOR SHARE;
    IF NOT FOUND
       OR candidate.repo_slug <> NEW.repo_slug
       OR candidate.namespace_kind <> NEW.namespace_kind
       OR candidate.namespace_key <> NEW.namespace_key
       OR candidate.embedder_model <> NEW.embedder_model
       OR candidate.embedding_dim <> NEW.embedding_dim
       OR candidate.policy_fingerprint <> NEW.policy_fingerprint
       OR candidate.pipeline_fingerprint <> NEW.pipeline_fingerprint
       OR candidate.embedder_fingerprint <> NEW.embedder_fingerprint
       OR candidate.policy_fingerprint = repeat('0', 64)
       OR candidate.pipeline_fingerprint = repeat('0', 64)
       OR candidate.embedder_fingerprint = repeat('0', 64) THEN
        RAISE EXCEPTION 'incompatible semantic index parent'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER code_search_indexes_parent_guard
BEFORE UPDATE OF
    parent_index_id, repo_slug, namespace_kind, namespace_key,
    embedder_model, embedding_dim, policy_fingerprint,
    pipeline_fingerprint, embedder_fingerprint
ON code_search_indexes
FOR EACH ROW EXECUTE FUNCTION validate_code_search_parent();

CREATE TRIGGER code_search_indexes_parent_insert_guard
BEFORE INSERT ON code_search_indexes
FOR EACH ROW EXECUTE FUNCTION validate_code_search_parent();

-- Physical target contract (created per operation, not by migration 030):
--
-- Final table name:
--   code_chunks__i_<32 lowercase UUID hex>
-- Attempt table name:
--   ccs__<32 lowercase UUID hex>__<positive attempt_count>
--
-- Both tables contain:
--   id text PRIMARY KEY                  -- path-aware stable chunk ID
--   file_path text NOT NULL              -- normalized repository-relative path
--   language text NOT NULL
--   content text NOT NULL
--   start_line integer NOT NULL
--   end_line integer NOT NULL
--   embedding vector(<record dimension>) NOT NULL
--
-- Every attempt table has an HNSW cosine index on embedding. Per-file writes
-- transactionally delete and replace that file's rows. Copy-forward inserts
-- only paths whose published parent manifest has the same blob/content digest
-- and whose new policy decision remains eligible.
--
-- Fenced publish is one transaction under a Postgres advisory xact lock keyed
-- by index_id:
--   1. lock and validate current index lease_token + attempt_count;
--   2. independently verify attempt schema, dimension, HNSW, manifest coverage,
--      and row/chunk counts;
--   3. drop only an unready prior final table, if present;
--   4. ALTER TABLE attempt_name RENAME TO final_name;
--   5. replace code_search_index_files from this attempt's manifest;
--   6. delete older attempt manifests and commit;
--   7. mark_ready with the same current lease token.
-- A stale attempt can only mutate its own attempt table/manifest and cannot
-- perform steps 3-6.

-- Runtime operation contract (implemented in the registry repository):
-- renew_index_lease(index_id, lease_token, lease_duration)
--   * updates lease_expires_at only while status='indexing'
--   * requires the current unexpired lease token
--   * does not change attempt_count or lifecycle status
--
-- find_compatible_parents(identity)
--   * matches all identity/fingerprint fields and status='ready'
--   * excludes the 64-zero legacy fingerprint sentinel
--   * application verifies Git ancestry before choosing a parent
