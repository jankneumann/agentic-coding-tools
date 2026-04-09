-- Migration 020: Merge train indexes (speculative-merge-trains task 5.7)
-- Dependencies: 012_feature_registry.sql
--
-- The merge train engine stores per-feature train state inside
-- feature_registry.metadata->'merge_queue' as JSONB. The periodic
-- compose_train() sweep and the get_train_status() query both need to
-- answer two questions fast:
--
--   Q1: "Give me every feature with train_id = 'abc123'"
--       — used by get_train_status(), eject_from_train(), crash recovery
--   Q2: "Within a train, give me entries sorted by (partition_id, train_position)"
--       — used by the wave merge algorithm in compose_train()
--
-- Without indexes these queries degenerate to a full scan of feature_registry.
-- We add three expression indexes to support them, plus a GIN index on the
-- merge_queue sub-document for @> containment queries (useful for ad-hoc
-- debugging / future filters).

-- =============================================================================
-- GIN index on the merge_queue sub-document
-- =============================================================================
-- Supports containment queries such as:
--   SELECT * FROM feature_registry
--   WHERE metadata -> 'merge_queue' @> '{"train_id": "abc123"}'::jsonb;
--
-- The GIN index indexes every (key, value) pair inside merge_queue, so any
-- containment query hits the index. Slightly larger than a targeted BTREE
-- but far more flexible for ad-hoc queries.
CREATE INDEX IF NOT EXISTS idx_feature_registry_merge_queue_gin
    ON feature_registry
    USING GIN ((metadata -> 'merge_queue'));

-- =============================================================================
-- BTREE expression indexes for targeted lookups
-- =============================================================================
-- train_id lookup: the hottest query path. get_train_status, eject_from_train,
-- and the compose_train sweep all filter on this.
CREATE INDEX IF NOT EXISTS idx_feature_registry_merge_queue_train_id
    ON feature_registry
    ((metadata -> 'merge_queue' ->> 'train_id'));

-- partition_id lookup: used to group entries within a train for wave scheduling.
CREATE INDEX IF NOT EXISTS idx_feature_registry_merge_queue_partition_id
    ON feature_registry
    ((metadata -> 'merge_queue' ->> 'partition_id'));

-- train_position sorting: the wave algorithm sorts entries by position within
-- a partition. Cast to int so BTREE orders numerically (lexicographic string
-- ordering would place '10' before '2').
CREATE INDEX IF NOT EXISTS idx_feature_registry_merge_queue_train_position
    ON feature_registry
    ((((metadata -> 'merge_queue' ->> 'train_position'))::int));

-- =============================================================================
-- EXPLAIN ANALYZE verification (operator-run, not automated)
-- =============================================================================
-- Run these in psql after applying the migration against a representative
-- dataset (≥100 queued features) to verify index usage. Replace the literal
-- values with something that exists in your data. Expected plan: Index Scan
-- on the relevant index, NOT Seq Scan. If you see Seq Scan, check that the
-- JSONB path expression matches exactly (Postgres is picky about the cast).
--
-- Q1: find all entries in a train
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT feature_id FROM feature_registry
--   WHERE (metadata -> 'merge_queue' ->> 'train_id') = '<some-train-id>';
--
-- Q2: order-within-partition lookup
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT feature_id,
--          (metadata -> 'merge_queue' ->> 'train_position')::int AS pos
--   FROM feature_registry
--   WHERE (metadata -> 'merge_queue' ->> 'train_id') = '<some-train-id>'
--     AND (metadata -> 'merge_queue' ->> 'partition_id') = '<some-partition>'
--   ORDER BY pos;
--
-- Q3: containment (GIN)
--   EXPLAIN (ANALYZE, BUFFERS)
--   SELECT feature_id FROM feature_registry
--   WHERE metadata -> 'merge_queue' @> '{"status": "speculating"}'::jsonb;
