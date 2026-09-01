-- Contract for ri-08 work-queue projection identity and reconciliation.
-- Source: https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT

CREATE UNIQUE INDEX work_queue_projection_key_uidx
ON work_queue (
    (input_data ->> 'change_id'),
    (input_data ->> 'phase'),
    ((input_data ->> 'iteration')::integer)
)
WHERE input_data ? 'change_id'
  AND input_data ? 'phase'
  AND input_data ? 'iteration'
  AND jsonb_typeof(input_data -> 'iteration') = 'number';

-- Existing submit_task signature remains callable. Its JSON result gains:
--   created boolean
--   deduplicated boolean
-- A complete projection key is insert-if-absent; incomplete/unkeyed payloads insert normally.

-- New RPC contract (body implemented in migration 035_work_queue_projection.sql):
CREATE OR REPLACE FUNCTION reconcile_work_projection(
    p_change_id TEXT,
    p_phase TEXT,
    p_iteration INTEGER,
    p_task_type TEXT,
    p_description TEXT,
    p_input_data JSONB,
    p_priority INTEGER DEFAULT 5,
    p_agent_requirements JSONB DEFAULT NULL
) RETURNS JSONB;

-- Result object:
-- {
--   "success": true,
--   "task_id": "uuid",
--   "created": true|false,
--   "deduplicated": false|true,
--   "cancelled_task_ids": ["uuid", ...]
-- }
