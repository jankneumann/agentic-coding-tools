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

-- The agent_heartbeat() RPC (023_add_phase_archetype.sql, Step 3) carries its
-- OWN hardcoded archetype allow-list and returns a structured
-- 'invalid_phase_archetype' error before the table CHECK ever runs. Widening
-- only the CHECK above would still let the heartbeat persistence path reject
-- p_phase_archetype='gatekeeper', so the new archetype would never reach
-- agent_sessions / discovery. Recreate the function with the widened list.
CREATE OR REPLACE FUNCTION agent_heartbeat(
    p_session_id TEXT DEFAULT NULL,
    p_agent_id TEXT DEFAULT NULL,
    p_phase_archetype TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    -- Validate phase_archetype against enum if provided. Returning a structured
    -- error here is friendlier than letting the CHECK constraint raise at
    -- COMMIT time, but the constraint remains as defense-in-depth.
    IF p_phase_archetype IS NOT NULL
       AND p_phase_archetype NOT IN (
            'architect', 'reviewer', 'implementer', 'analyst',
            'runner', 'gatekeeper'
       ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'invalid_phase_archetype',
            'value', p_phase_archetype
        );
    END IF;

    UPDATE agent_sessions
       SET last_heartbeat = NOW(),
           status = 'active',
           phase_archetype = COALESCE(p_phase_archetype, phase_archetype)
     WHERE (p_session_id IS NOT NULL AND id = p_session_id)
        OR (p_session_id IS NULL AND p_agent_id IS NOT NULL AND agent_id = p_agent_id);

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated > 0 THEN
        RETURN jsonb_build_object(
            'success', true,
            'session_id', p_session_id
        );
    ELSE
        RETURN jsonb_build_object(
            'success', false,
            'error', 'session_not_found'
        );
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMIT;
