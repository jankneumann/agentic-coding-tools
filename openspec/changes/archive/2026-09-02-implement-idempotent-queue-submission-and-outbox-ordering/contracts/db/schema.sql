-- ri-08 projection identity contract. Public callers provide projection_key;
-- the service alone materializes these reserved fields in input_data.
CREATE TABLE work_queue_projection_heads (
    change_id TEXT PRIMARY KEY,
    phase TEXT NOT NULL,
    transition_sequence INTEGER NOT NULL CHECK (transition_sequence >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX work_queue_projection_key_uidx
ON work_queue (
    (input_data ->> 'change_id'),
    (input_data ->> 'phase'),
    (input_data ->> 'transition_sequence')
)
WHERE input_data ? 'change_id'
  AND input_data ? 'phase'
  AND input_data ? 'transition_sequence'
  AND jsonb_typeof(input_data -> 'transition_sequence') = 'number';

-- Keyed submit_task and reconcile_work_projection MUST first execute:
-- SELECT pg_advisory_xact_lock(hashtextextended(p_change_id, 0));
-- submit_task establishes a missing head and thereafter accepts only the exact
-- equal (phase, transition_sequence) generation. It raises stale_projection
-- below the head, projection_generation_mismatch for equal-sequence/different-
-- phase requests, and reconciliation_required above the head.
-- reconcile rejects below-head requests and otherwise advances both head fields.
-- Keyed insertion MUST use this exact arbiter:
-- ON CONFLICT ((input_data ->> 'change_id'),
--              (input_data ->> 'phase'),
--              (input_data ->> 'transition_sequence'))
-- WHERE input_data ? 'change_id'
--   AND input_data ? 'phase'
--   AND input_data ? 'transition_sequence'
--   AND jsonb_typeof(input_data -> 'transition_sequence') = 'number'
-- DO NOTHING;
-- Canonical lookup MUST repeat the same expressions/predicate and compare the
-- validated change_id, phase, and transition_sequence::text values.

CREATE OR REPLACE FUNCTION reconcile_work_projection(
    p_change_id TEXT,
    p_phase TEXT,
    p_transition_sequence INTEGER,
    p_task_type TEXT,
    p_description TEXT,
    p_input_data JSONB,
    p_priority INTEGER DEFAULT 5,
    p_agent_requirements JSONB DEFAULT NULL
) RETURNS JSONB;

-- Migration 035 runs in one transaction under SHARE ROW EXCLUSIVE lock. Before
-- index creation it rejects partial/malformed/out-of-range keys (SQLSTATE 23514)
-- and duplicate valid complete keys (23505), reporting offending task IDs.
-- Failure rolls back; operators quarantine/normalize those rows and retry the
-- unchanged migration. Terminal current rows, including cancelled, are already
-- satisfied and are returned rather than replaced.
