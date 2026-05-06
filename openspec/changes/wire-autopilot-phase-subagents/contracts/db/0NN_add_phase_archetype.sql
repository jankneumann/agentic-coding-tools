-- Migration: add phase_archetype column to agent_sessions
-- Change: wire-autopilot-phase-subagents (D-1)
-- Replace 0NN with next available sequence number when committing into
-- agent-coordinator/database/migrations/. The implementer in
-- wp-coordinator-status-discovery is responsible for choosing a number
-- that is the max+1 of the existing migrations directory at PR-creation
-- time and verifying no parallel PR has claimed the same number.

BEGIN;

ALTER TABLE agent_sessions
    ADD COLUMN IF NOT EXISTS phase_archetype TEXT
        CONSTRAINT phase_archetype_enum
            CHECK (
                phase_archetype IS NULL
                OR phase_archetype IN (
                    'architect', 'reviewer', 'implementer', 'analyst', 'runner'
                )
            )
        CONSTRAINT phase_archetype_length
            CHECK (phase_archetype IS NULL OR LENGTH(phase_archetype) <= 32);

-- Why two CHECK constraints rather than one combined check?
-- Naming each constraint produces clearer Postgres error messages:
-- a violation of phase_archetype_enum vs phase_archetype_length tells
-- the operator immediately whether the issue is a typo (enum) or
-- payload abuse (length).

-- Index is intentionally omitted: phase_archetype is low-cardinality
-- (5 values: architect, reviewer, implementer, analyst, runner) and the
-- existing primary-key + agent_id index already supports the queries we
-- expect (lookup by agent_id, listing all agents). If observability
-- queries grow to need filtering by archetype across all agents, add a
-- partial index in a follow-up.

COMMIT;
