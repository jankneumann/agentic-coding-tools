-- Migration: add phase_archetype to agent_sessions + update discover_agents RPC
-- Change: wire-autopilot-phase-subagents (D-1)
-- Replace 0NN with next available sequence number when committing into
-- agent-coordinator/database/migrations/. The implementer in
-- wp-coordinator-status-discovery is responsible for choosing a number
-- that is the max+1 of the existing migrations directory at PR-creation
-- time and verifying no parallel PR has claimed the same number.

BEGIN;

-- Step 1: Add the column.
-- The single CHECK constraint enforces both enum membership and length;
-- enum-only would already cap length implicitly (max value is 11 chars,
-- 'implementer'), but we leave the explicit length cap in place as
-- defense-in-depth against migration drift if a new archetype is added
-- later that would exceed reasonable bounds.
ALTER TABLE agent_sessions
    ADD COLUMN IF NOT EXISTS phase_archetype TEXT
        CONSTRAINT phase_archetype_valid
            CHECK (
                phase_archetype IS NULL
                OR (
                    phase_archetype IN (
                        'architect', 'reviewer', 'implementer', 'analyst', 'runner'
                    )
                    AND LENGTH(phase_archetype) <= 64  -- aligns with API max_length=64
                )
            );

-- Step 2: Update discover_agents() RPC to surface phase_archetype.
-- The existing function (003_agent_discovery.sql) builds its JSONB
-- response by hand, so the new column won't reach GET /discovery/agents
-- consumers without this update.
CREATE OR REPLACE FUNCTION discover_agents(
    p_capability TEXT DEFAULT NULL,
    p_status TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_agents JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'agent_id', s.agent_id,
            'agent_type', s.agent_type,
            'session_id', s.id,
            'capabilities', s.capabilities,
            'status', s.status,
            'current_task', s.current_task,
            'last_heartbeat', s.last_heartbeat,
            'started_at', s.started_at,
            'phase_archetype', s.phase_archetype
        )
        ORDER BY s.last_heartbeat DESC
    ), '[]'::jsonb)
    INTO v_agents
    FROM agent_sessions s
    WHERE (p_capability IS NULL OR p_capability = ANY(s.capabilities))
      AND ((p_status IS NOT NULL AND s.status = p_status)
           OR (p_status IS NULL AND s.status != 'disconnected'));

    RETURN jsonb_build_object('agents', v_agents);
END;
$$ LANGUAGE plpgsql;

-- Step 3: Update agent_heartbeat() RPC to accept and persist phase_archetype.
-- The Python DiscoveryService.heartbeat() will pass the value through;
-- without RPC support it would be silently dropped.
-- We define the new signature as a SUPERSET of the existing one — the
-- original `agent_heartbeat(p_session_id, p_agent_id)` still works
-- because p_phase_archetype defaults to NULL.
CREATE OR REPLACE FUNCTION agent_heartbeat(
    p_session_id UUID DEFAULT NULL,
    p_agent_id TEXT DEFAULT NULL,
    p_phase_archetype TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    -- Validate phase_archetype against enum if provided
    IF p_phase_archetype IS NOT NULL
       AND p_phase_archetype NOT IN ('architect', 'reviewer', 'implementer', 'analyst', 'runner') THEN
        RETURN jsonb_build_object(
            'ok', false,
            'error', 'invalid_phase_archetype',
            'value', p_phase_archetype
        );
    END IF;

    UPDATE agent_sessions
       SET last_heartbeat = NOW(),
           phase_archetype = COALESCE(p_phase_archetype, phase_archetype)
     WHERE (p_session_id IS NOT NULL AND id = p_session_id)
        OR (p_session_id IS NULL AND p_agent_id IS NOT NULL AND agent_id = p_agent_id);

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated = 0 THEN
        RETURN jsonb_build_object('ok', false, 'error', 'agent_not_found');
    END IF;

    RETURN jsonb_build_object('ok', true, 'updated', v_updated);
END;
$$ LANGUAGE plpgsql;

-- Why COALESCE(p_phase_archetype, phase_archetype)?
-- Older heartbeat callers that don't pass phase_archetype would
-- otherwise overwrite the existing value with NULL on every heartbeat.
-- Using COALESCE means: if you pass a value, we update; if you pass
-- NULL (explicit or default), we keep what was there.

-- Index is intentionally omitted: phase_archetype is low-cardinality
-- (5 values) and the existing primary-key + agent_id index already
-- supports the queries we expect. If observability queries grow to
-- need filtering by archetype across all agents at scale, add a
-- partial index in a follow-up.

COMMIT;
