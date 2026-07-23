-- Migration 030: fingerprinted incremental semantic-index manifests.
--
-- Migration 029 introduced immutable revision identities. This additive
-- migration makes every computation-affecting contract part of identity and
-- adds attempt-scoped plus published file manifests. Existing rows receive an
-- explicit legacy sentinel and are never eligible for compatible-parent reuse.

ALTER TABLE code_search_registry
    ADD COLUMN IF NOT EXISTS git_common_dir_fingerprint TEXT;

UPDATE code_search_registry
SET git_common_dir_fingerprint = repeat('0', 64)
WHERE git_common_dir_fingerprint IS NULL;

ALTER TABLE code_search_registry
    ALTER COLUMN git_common_dir_fingerprint SET NOT NULL;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'code_search_registry_git_common_dir_fingerprint_ck'
          AND conrelid = 'code_search_registry'::regclass
    ) THEN
        ALTER TABLE code_search_registry
            ADD CONSTRAINT code_search_registry_git_common_dir_fingerprint_ck
            CHECK (git_common_dir_fingerprint ~ '^[0-9a-f]{64}$');
    END IF;
END;
$migration$;

CREATE OR REPLACE FUNCTION validate_code_search_repository_identity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.repo_root IS DISTINCT FROM OLD.repo_root THEN
        RAISE EXCEPTION 'repository root identity is immutable'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.git_common_dir_fingerprint
           IS DISTINCT FROM OLD.git_common_dir_fingerprint
       AND NOT (
           OLD.git_common_dir_fingerprint = repeat('0', 64)
           AND NEW.git_common_dir_fingerprint <> repeat('0', 64)
       ) THEN
        RAISE EXCEPTION
            'repository git common-directory identity is immutable'
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
        WHERE tgname = 'code_search_registry_identity_guard'
          AND tgrelid = 'code_search_registry'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER code_search_registry_identity_guard
        BEFORE UPDATE OF repo_root, git_common_dir_fingerprint
        ON code_search_registry
        FOR EACH ROW EXECUTE FUNCTION validate_code_search_repository_identity();
    END IF;
END;
$migration$;

ALTER TABLE code_search_indexes
    ADD COLUMN IF NOT EXISTS policy_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS pipeline_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS embedder_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS parent_index_id UUID;

UPDATE code_search_indexes
SET policy_fingerprint = repeat('0', 64)
WHERE policy_fingerprint IS NULL;

UPDATE code_search_indexes
SET pipeline_fingerprint = repeat('0', 64)
WHERE pipeline_fingerprint IS NULL;

UPDATE code_search_indexes
SET embedder_fingerprint = repeat('0', 64)
WHERE embedder_fingerprint IS NULL;

ALTER TABLE code_search_indexes
    ALTER COLUMN policy_fingerprint SET NOT NULL,
    ALTER COLUMN pipeline_fingerprint SET NOT NULL,
    ALTER COLUMN embedder_fingerprint SET NOT NULL;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'code_search_indexes_policy_fingerprint_ck'
          AND conrelid = 'code_search_indexes'::regclass
    ) THEN
        ALTER TABLE code_search_indexes
            ADD CONSTRAINT code_search_indexes_policy_fingerprint_ck
            CHECK (policy_fingerprint ~ '^[0-9a-f]{64}$');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'code_search_indexes_pipeline_fingerprint_ck'
          AND conrelid = 'code_search_indexes'::regclass
    ) THEN
        ALTER TABLE code_search_indexes
            ADD CONSTRAINT code_search_indexes_pipeline_fingerprint_ck
            CHECK (pipeline_fingerprint ~ '^[0-9a-f]{64}$');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'code_search_indexes_embedder_fingerprint_ck'
          AND conrelid = 'code_search_indexes'::regclass
    ) THEN
        ALTER TABLE code_search_indexes
            ADD CONSTRAINT code_search_indexes_embedder_fingerprint_ck
            CHECK (embedder_fingerprint ~ '^[0-9a-f]{64}$');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'code_search_indexes_parent_not_self_ck'
          AND conrelid = 'code_search_indexes'::regclass
    ) THEN
        ALTER TABLE code_search_indexes
            ADD CONSTRAINT code_search_indexes_parent_not_self_ck
            CHECK (parent_index_id IS NULL OR parent_index_id <> index_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'code_search_indexes_parent_fk'
          AND conrelid = 'code_search_indexes'::regclass
    ) THEN
        ALTER TABLE code_search_indexes
            ADD CONSTRAINT code_search_indexes_parent_fk
            FOREIGN KEY (parent_index_id)
            REFERENCES code_search_indexes(index_id)
            ON DELETE RESTRICT;
    END IF;
END;
$migration$;

ALTER TABLE code_search_indexes
    DROP CONSTRAINT IF EXISTS code_search_indexes_natural_key;

ALTER TABLE code_search_indexes
    ADD CONSTRAINT code_search_indexes_natural_key UNIQUE (
        repo_slug, namespace_kind, namespace_key, source_revision,
        embedder_model, embedding_dim, policy_fingerprint,
        pipeline_fingerprint, embedder_fingerprint
    );

CREATE INDEX IF NOT EXISTS code_search_indexes_compatible_parent_idx
    ON code_search_indexes (
        repo_slug, namespace_kind, namespace_key, embedder_model,
        embedding_dim, policy_fingerprint, pipeline_fingerprint,
        embedder_fingerprint, completed_at DESC
    )
    WHERE status = 'ready';

CREATE TABLE IF NOT EXISTS code_search_index_file_attempts (
    index_id UUID NOT NULL
        REFERENCES code_search_indexes(index_id) ON DELETE CASCADE,
    attempt_count INTEGER NOT NULL CHECK (attempt_count > 0),
    file_path TEXT NOT NULL,
    git_blob_id TEXT,
    git_entry_type TEXT
        CHECK (git_entry_type IS NULL OR git_entry_type IN ('blob', 'symlink')),
    eligible BOOLEAN NOT NULL,
    eligibility_reason TEXT NOT NULL CHECK (eligibility_reason <> ''),
    content_digest TEXT,
    chunk_digest TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
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
        OR (NOT eligible AND chunk_count = 0)
    )
);

CREATE TABLE IF NOT EXISTS code_search_index_files (
    index_id UUID NOT NULL
        REFERENCES code_search_indexes(index_id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    git_blob_id TEXT,
    git_entry_type TEXT
        CHECK (git_entry_type IS NULL OR git_entry_type IN ('blob', 'symlink')),
    eligible BOOLEAN NOT NULL,
    eligibility_reason TEXT NOT NULL CHECK (eligibility_reason <> ''),
    content_digest TEXT,
    chunk_digest TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
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
        OR (NOT eligible AND chunk_count = 0)
    )
);

CREATE INDEX IF NOT EXISTS code_search_index_files_blob_idx
    ON code_search_index_files (index_id, git_blob_id)
    WHERE eligible;

CREATE OR REPLACE FUNCTION validate_code_search_parent()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
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

    SELECT *
    INTO candidate
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
END;
$function$;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'code_search_indexes_parent_guard'
          AND tgrelid = 'code_search_indexes'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER code_search_indexes_parent_guard
        BEFORE UPDATE OF
            parent_index_id, repo_slug, namespace_kind, namespace_key,
            embedder_model, embedding_dim, policy_fingerprint,
            pipeline_fingerprint, embedder_fingerprint
        ON code_search_indexes
        FOR EACH ROW EXECUTE FUNCTION validate_code_search_parent();
    END IF;
END;
$migration$;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'code_search_indexes_parent_insert_guard'
          AND tgrelid = 'code_search_indexes'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER code_search_indexes_parent_insert_guard
        BEFORE INSERT
        ON code_search_indexes
        FOR EACH ROW EXECUTE FUNCTION validate_code_search_parent();
    END IF;
END;
$migration$;

CREATE OR REPLACE FUNCTION validate_code_search_parent_target()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM code_search_indexes AS child
        WHERE child.parent_index_id = NEW.index_id
          AND (
              NEW.status <> 'ready'
              OR child.repo_slug <> NEW.repo_slug
              OR child.namespace_kind <> NEW.namespace_kind
              OR child.namespace_key <> NEW.namespace_key
              OR child.embedder_model <> NEW.embedder_model
              OR child.embedding_dim <> NEW.embedding_dim
              OR child.policy_fingerprint <> NEW.policy_fingerprint
              OR child.pipeline_fingerprint <> NEW.pipeline_fingerprint
              OR child.embedder_fingerprint <> NEW.embedder_fingerprint
          )
    ) THEN
        RAISE EXCEPTION
            'referenced semantic index parent must remain compatible and ready'
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
        WHERE tgname = 'code_search_indexes_parent_target_guard'
          AND tgrelid = 'code_search_indexes'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE CONSTRAINT TRIGGER code_search_indexes_parent_target_guard
        AFTER UPDATE OF
            repo_slug, namespace_kind, namespace_key, embedder_model,
            embedding_dim, policy_fingerprint, pipeline_fingerprint,
            embedder_fingerprint, status
        ON code_search_indexes
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION validate_code_search_parent_target();
    END IF;
END;
$migration$;

COMMENT ON COLUMN code_search_indexes.policy_fingerprint IS
    'SHA-256 of the canonical index-time eligibility policy; all zeroes means legacy.';
COMMENT ON COLUMN code_search_indexes.pipeline_fingerprint IS
    'SHA-256 of the canonical chunking/storage compatibility contract; all zeroes means legacy.';
COMMENT ON COLUMN code_search_indexes.embedder_fingerprint IS
    'SHA-256 of the non-secret embedding contract; all zeroes means legacy.';
COMMENT ON TABLE code_search_index_file_attempts IS
    'Lease-attempt-scoped file manifests; never visible to ready-only readers.';
COMMENT ON TABLE code_search_index_files IS
    'Published immutable file manifest for one ready semantic index.';
COMMENT ON COLUMN code_search_registry.git_common_dir_fingerprint IS
    'SHA-256 of the canonical Git common-directory path. All zeroes marks '
    'legacy metadata awaiting a same-root one-time upgrade.';
