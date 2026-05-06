-- Migration: add phase_archetype column to agent_sessions
-- Change: wire-autopilot-phase-subagents (D-1)
-- Replace 0NN with next available sequence number when committing into
-- agent-coordinator/database/migrations/.

BEGIN;

ALTER TABLE agent_sessions
    ADD COLUMN IF NOT EXISTS phase_archetype TEXT;

-- Index is intentionally omitted: phase_archetype is low-cardinality
-- (5 values: architect, reviewer, implementer, analyst, runner) and the
-- existing primary-key + agent_id index already supports the queries we
-- expect (lookup by agent_id, listing all agents). If observability
-- queries grow to need filtering by archetype across all agents, add a
-- partial index in a follow-up.

COMMIT;
