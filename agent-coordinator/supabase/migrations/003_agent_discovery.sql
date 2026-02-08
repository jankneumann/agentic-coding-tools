-- Agent Discovery: Extend agent_sessions for discovery, heartbeat, and dead agent detection
-- Adds capabilities, status, heartbeat, and cleanup functions.

-- =============================================================================
-- ALTER agent_sessions: Add discovery and heartbeat columns
-- =============================================================================

ALTER TABLE agent_sessions
    ADD COLUMN capabilities TEXT[] DEFAULT '{}',
    ADD COLUMN status TEXT DEFAULT 'active' CHECK (status IN ('active', 'idle', 'disconnected')),
    ADD COLUMN last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN current_task TEXT;

CREATE INDEX idx_agent_sessions_status ON agent_sessions(status);
CREATE INDEX idx_agent_sessions_heartbeat ON agent_sessions(last_heartbeat);
CREATE INDEX idx_agent_sessions_capabilities ON agent_sessions USING GIN(capabilities);


-- =============================================================================
-- FUNCTIONS: Agent registration and discovery
-- =============================================================================

-- Register or update an agent session with capabilities
CREATE OR REPLACE FUNCTION register_agent_session(
    p_agent_id TEXT,
    p_agent_type TEXT,
    p_session_id TEXT DEFAULT NULL,
    p_capabilities TEXT[] DEFAULT '{}',
    p_current_task TEXT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_session_id TEXT;
BEGIN
    v_session_id := COALESCE(p_session_id, p_agent_id || '-' || gen_random_uuid()::TEXT);

    INSERT INTO agent_sessions (id, agent_id, agent_type, capabilities, status, last_heartbeat, current_task)
    VALUES (v_session_id, p_agent_id, p_agent_type, p_capabilities, 'active', NOW(), p_current_task)
    ON CONFLICT (id) DO UPDATE SET
        capabilities = EXCLUDED.capabilities,
        status = 'active',
        last_heartbeat = NOW(),
        current_task = EXCLUDED.current_task;

    RETURN jsonb_build_object(
        'success', true,
        'session_id', v_session_id
    );
END;
$$ LANGUAGE plpgsql;


-- Discover agents with optional filtering
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
            'started_at', s.started_at
        )
        ORDER BY s.last_heartbeat DESC
    ), '[]'::jsonb)
    INTO v_agents
    FROM agent_sessions s
    WHERE (p_capability IS NULL OR p_capability = ANY(s.capabilities))
      AND (p_status IS NOT NULL AND s.status = p_status
           OR p_status IS NULL AND s.status != 'disconnected');

    RETURN jsonb_build_object(
        'agents', v_agents
    );
END;
$$ LANGUAGE plpgsql;


-- Update heartbeat timestamp
CREATE OR REPLACE FUNCTION agent_heartbeat(
    p_session_id TEXT
) RETURNS JSONB AS $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE agent_sessions
    SET last_heartbeat = NOW(),
        status = 'active'
    WHERE id = p_session_id;

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


-- Clean up dead agents: mark as disconnected and release their locks
CREATE OR REPLACE FUNCTION cleanup_dead_agents(
    p_stale_threshold INTERVAL DEFAULT '15 minutes'
) RETURNS JSONB AS $$
DECLARE
    v_cleaned INTEGER;
    v_locks_released INTEGER;
    v_stale_agent_ids TEXT[];
BEGIN
    -- Identify stale agents first
    SELECT ARRAY_AGG(agent_id)
    INTO v_stale_agent_ids
    FROM agent_sessions
    WHERE status IN ('active', 'idle')
      AND last_heartbeat < NOW() - p_stale_threshold;

    -- Nothing to clean up
    IF v_stale_agent_ids IS NULL THEN
        RETURN jsonb_build_object(
            'success', true,
            'agents_cleaned', 0,
            'locks_released', 0
        );
    END IF;

    -- Mark stale agents as disconnected
    UPDATE agent_sessions
    SET status = 'disconnected'
    WHERE agent_id = ANY(v_stale_agent_ids);

    GET DIAGNOSTICS v_cleaned = ROW_COUNT;

    -- Release locks held only by the newly-disconnected agents
    DELETE FROM file_locks
    WHERE locked_by = ANY(v_stale_agent_ids);

    GET DIAGNOSTICS v_locks_released = ROW_COUNT;

    RETURN jsonb_build_object(
        'success', true,
        'agents_cleaned', v_cleaned,
        'locks_released', v_locks_released
    );
END;
$$ LANGUAGE plpgsql;
