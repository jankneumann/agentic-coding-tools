-- Migration: extend agent_sessions.phase_archetype enum with 'gatekeeper'
-- Change: autopilot-complexity-gate (GATEKEEPER judge gate)
--
-- The GATEKEEPER phase replaces deterministic complexity blocking with a
-- model-based verifiability/risk judgment, dispatched under a new 'gatekeeper'
-- archetype. The phase_archetype CHECK constraint added in
-- 023_add_phase_archetype.sql enumerates the allowed archetype values, so it
-- must be widened or status reports carrying phase_archetype='gatekeeper' would
-- be rejected. Keep the value list in sync with:
--   - agent-coordinator/archetypes.yaml :: archetypes / phase_mapping
--   - agent-coordinator/scripts/report_status.py :: _VALID_PHASE_ARCHETYPES
--   - agent-coordinator/src/coordination_api.py :: StatusReportRequest.phase_archetype

BEGIN;

-- Postgres CHECK constraints are immutable in place; drop and re-add with the
-- widened enum. IF EXISTS keeps the migration idempotent across re-runs.
ALTER TABLE agent_sessions
    DROP CONSTRAINT IF EXISTS phase_archetype_valid;

ALTER TABLE agent_sessions
    ADD CONSTRAINT phase_archetype_valid
        CHECK (
            phase_archetype IS NULL
            OR (
                phase_archetype IN (
                    'architect', 'reviewer', 'implementer', 'analyst',
                    'runner', 'gatekeeper'
                )
                AND LENGTH(phase_archetype) <= 64  -- aligns with API max_length=64
            )
        );

COMMIT;
