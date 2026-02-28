-- Feature Registry for Cross-Feature Coordination
-- Tracks active features and their resource claims (lock keys)
-- for conflict detection and parallel feasibility analysis.

-- =============================================================================
-- FEATURE REGISTRY: Cross-feature resource claim management
-- =============================================================================

CREATE TABLE feature_registry (
    feature_id TEXT PRIMARY KEY,              -- e.g. "add-auth-system"
    title TEXT,                                -- Human-readable title
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active', 'completed', 'cancelled')
    ),
    registered_by TEXT NOT NULL,               -- agent_id of registrant
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Resource claims — array of lock keys (files + logical keys)
    resource_claims TEXT[] NOT NULL DEFAULT '{}',

    -- Branch name for merge ordering
    branch_name TEXT,

    -- Merge priority (lower = merges first)
    merge_priority INTEGER DEFAULT 5 CHECK (merge_priority BETWEEN 1 AND 10),

    -- Metadata (plan revision, contracts revision, etc.)
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_feature_registry_status ON feature_registry(status);
CREATE INDEX idx_feature_registry_registered_by ON feature_registry(registered_by);

-- =============================================================================
-- RPC: Register a feature with resource claims
-- =============================================================================

CREATE OR REPLACE FUNCTION register_feature(
    p_feature_id TEXT,
    p_title TEXT DEFAULT NULL,
    p_agent_id TEXT DEFAULT 'unknown',
    p_resource_claims TEXT[] DEFAULT '{}',
    p_branch_name TEXT DEFAULT NULL,
    p_merge_priority INTEGER DEFAULT 5,
    p_metadata JSONB DEFAULT '{}'
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_result JSONB;
BEGIN
    -- Upsert: if feature already exists and is active, update claims
    INSERT INTO feature_registry (
        feature_id, title, registered_by, resource_claims,
        branch_name, merge_priority, metadata
    )
    VALUES (
        p_feature_id, p_title, p_agent_id, p_resource_claims,
        p_branch_name, p_merge_priority, p_metadata
    )
    ON CONFLICT (feature_id) DO UPDATE SET
        title = COALESCE(EXCLUDED.title, feature_registry.title),
        resource_claims = EXCLUDED.resource_claims,
        branch_name = COALESCE(EXCLUDED.branch_name, feature_registry.branch_name),
        merge_priority = EXCLUDED.merge_priority,
        metadata = feature_registry.metadata || EXCLUDED.metadata,
        updated_at = NOW()
    WHERE feature_registry.status = 'active';

    SELECT jsonb_build_object(
        'success', TRUE,
        'feature_id', p_feature_id,
        'action', CASE WHEN xmax = 0 THEN 'registered' ELSE 'updated' END
    ) INTO v_result
    FROM feature_registry
    WHERE feature_id = p_feature_id;

    RETURN COALESCE(v_result, jsonb_build_object(
        'success', FALSE,
        'reason', 'feature_not_active'
    ));
END;
$$;

-- =============================================================================
-- RPC: Complete/cancel a feature registration
-- =============================================================================

CREATE OR REPLACE FUNCTION deregister_feature(
    p_feature_id TEXT,
    p_status TEXT DEFAULT 'completed'
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_status NOT IN ('completed', 'cancelled') THEN
        RETURN jsonb_build_object(
            'success', FALSE,
            'reason', 'invalid_status'
        );
    END IF;

    UPDATE feature_registry
    SET status = p_status,
        completed_at = NOW(),
        updated_at = NOW()
    WHERE feature_id = p_feature_id
      AND status = 'active';

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', FALSE,
            'reason', 'feature_not_found_or_not_active'
        );
    END IF;

    RETURN jsonb_build_object(
        'success', TRUE,
        'feature_id', p_feature_id,
        'status', p_status
    );
END;
$$;
