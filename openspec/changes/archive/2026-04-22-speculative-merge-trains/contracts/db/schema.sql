-- Database contract: Speculative Merge Trains
-- No new tables required — train state is stored in feature_registry.metadata JSONB.
-- This migration adds a GIN index for efficient train_id lookups.

-- Index for querying train entries by train_id within the JSONB metadata
CREATE INDEX IF NOT EXISTS idx_feature_registry_train_id
ON feature_registry USING GIN ((metadata -> 'merge_queue' -> 'train_id'));

-- Index for querying by partition_id
CREATE INDEX IF NOT EXISTS idx_feature_registry_partition_id
ON feature_registry USING GIN ((metadata -> 'merge_queue' -> 'partition_id'));

-- Feature flags table (lightweight, version-controlled flags.yaml is source of truth)
-- This table is optional — only needed if flag resolution needs DB-backed overrides.
-- For Phase 1, flags.yaml + environment variables are sufficient.
