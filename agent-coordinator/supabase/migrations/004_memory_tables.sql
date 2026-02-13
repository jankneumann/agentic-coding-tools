-- Migration 004: Memory tables for episodic, working, and procedural memory
-- Dependencies: 001_core_schema.sql (agent_sessions reference)
-- Phase 2 feature: Agent memory for cross-session learning

-- =============================================================================
-- Tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS memory_episodic (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    session_id TEXT,
    event_type TEXT NOT NULL,  -- 'error', 'success', 'decision', 'discovery', 'optimization'
    summary TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    outcome TEXT,              -- 'positive', 'negative', 'neutral'
    lessons TEXT[],
    tags TEXT[] DEFAULT '{}',
    relevance_score FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_working (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, session_id, key)
);

CREATE TABLE IF NOT EXISTS memory_procedural (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]',
    prerequisites TEXT[] DEFAULT '{}',
    success_count INT DEFAULT 0,
    failure_count INT DEFAULT 0,
    last_used TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_memory_episodic_agent ON memory_episodic (agent_id);
CREATE INDEX IF NOT EXISTS idx_memory_episodic_event_type ON memory_episodic (event_type);
CREATE INDEX IF NOT EXISTS idx_memory_episodic_tags ON memory_episodic USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_memory_episodic_created ON memory_episodic (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_working_agent_session ON memory_working (agent_id, session_id);
CREATE INDEX IF NOT EXISTS idx_memory_procedural_skill ON memory_procedural (skill_name);

-- =============================================================================
-- Functions
-- =============================================================================

CREATE OR REPLACE FUNCTION store_episodic_memory(
    p_agent_id TEXT,
    p_session_id TEXT DEFAULT NULL,
    p_event_type TEXT DEFAULT 'discovery',
    p_summary TEXT DEFAULT '',
    p_details JSONB DEFAULT '{}',
    p_outcome TEXT DEFAULT NULL,
    p_lessons TEXT[] DEFAULT '{}',
    p_tags TEXT[] DEFAULT '{}'
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing UUID;
    v_memory_id UUID;
BEGIN
    -- Check for near-duplicate within 1 hour (deduplication)
    SELECT id INTO v_existing
    FROM memory_episodic
    WHERE agent_id = p_agent_id
      AND event_type = p_event_type
      AND summary = p_summary
      AND created_at > now() - interval '1 hour'
    LIMIT 1;

    IF v_existing IS NOT NULL THEN
        RETURN jsonb_build_object(
            'success', true,
            'memory_id', v_existing,
            'action', 'deduplicated'
        );
    END IF;

    INSERT INTO memory_episodic (agent_id, session_id, event_type, summary, details, outcome, lessons, tags)
    VALUES (p_agent_id, p_session_id, p_event_type, p_summary, p_details, p_outcome, p_lessons, p_tags)
    RETURNING id INTO v_memory_id;

    RETURN jsonb_build_object(
        'success', true,
        'memory_id', v_memory_id,
        'action', 'created'
    );
END;
$$;

CREATE OR REPLACE FUNCTION get_relevant_memories(
    p_agent_id TEXT DEFAULT NULL,
    p_tags TEXT[] DEFAULT '{}',
    p_event_type TEXT DEFAULT NULL,
    p_limit INT DEFAULT 10,
    p_min_relevance FLOAT DEFAULT 0.0
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(row_to_json(m))
    INTO v_result
    FROM (
        SELECT
            id, agent_id, event_type, summary, details, outcome, lessons, tags,
            relevance_score,
            -- Time-decay: reduce relevance by 10% per day
            relevance_score * EXP(-0.1 * EXTRACT(EPOCH FROM (now() - created_at)) / 86400) AS decayed_relevance,
            created_at
        FROM memory_episodic
        WHERE (p_agent_id IS NULL OR agent_id = p_agent_id)
          AND (p_event_type IS NULL OR event_type = p_event_type)
          AND (array_length(p_tags, 1) IS NULL OR tags && p_tags)
          AND relevance_score >= p_min_relevance
        ORDER BY decayed_relevance DESC, created_at DESC
        LIMIT p_limit
    ) m;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE memory_episodic ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_working ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_procedural ENABLE ROW LEVEL SECURITY;

-- Read access for all roles
CREATE POLICY memory_episodic_read ON memory_episodic FOR SELECT USING (true);
CREATE POLICY memory_working_read ON memory_working FOR SELECT USING (true);
CREATE POLICY memory_procedural_read ON memory_procedural FOR SELECT USING (true);

-- Write access for service_role only
CREATE POLICY memory_episodic_write ON memory_episodic FOR INSERT
    WITH CHECK (current_setting('role') = 'service_role');
CREATE POLICY memory_working_write ON memory_working FOR ALL
    USING (current_setting('role') = 'service_role');
CREATE POLICY memory_procedural_write ON memory_procedural FOR ALL
    USING (current_setting('role') = 'service_role');
