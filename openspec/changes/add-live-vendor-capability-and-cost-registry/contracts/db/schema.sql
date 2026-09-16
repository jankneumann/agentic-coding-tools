-- Contract-only projection; implementation migration is generated from this shape.
-- Intentionally contains no pricing columns: model_catalog remains the sole price owner.
CREATE TABLE IF NOT EXISTS vendor_probe_state (
    agent_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('available', 'unavailable', 'unknown')),
    source_agent_id TEXT NOT NULL,
    reason TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    stale_after TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS vendor_rate_limits (
    observation_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'lane' CHECK (scope IN ('lane', 'model')),
    model TEXT,
    reason TEXT NOT NULL,
    source_agent_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    reset_at TIMESTAMPTZ NOT NULL,
    payload_hash TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (scope <> 'model' OR model IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_vendor_rate_limits_active
    ON vendor_rate_limits (agent_id, reset_at);

-- Rows cease affecting reads at reset_at and are eligible for compaction after
-- reset_at + the configured seven-day audit-retention period.


CREATE OR REPLACE FUNCTION upsert_vendor_probe_state(
    p_agent_id TEXT,
    p_observation_id TEXT,
    p_status TEXT,
    p_source_agent_id TEXT,
    p_reason TEXT,
    p_observed_at TIMESTAMPTZ,
    p_stale_after TIMESTAMPTZ,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS SETOF vendor_probe_state
LANGUAGE sql AS $$
    INSERT INTO vendor_probe_state (
        agent_id, observation_id, status, source_agent_id, reason, observed_at, stale_after, metadata
    ) VALUES (
        p_agent_id, p_observation_id, p_status, p_source_agent_id, p_reason, p_observed_at, p_stale_after, p_metadata
    )
    ON CONFLICT (agent_id) DO UPDATE SET
        observation_id = EXCLUDED.observation_id,
        status = EXCLUDED.status,
        source_agent_id = EXCLUDED.source_agent_id,
        reason = EXCLUDED.reason,
        observed_at = EXCLUDED.observed_at,
        stale_after = EXCLUDED.stale_after,
        metadata = EXCLUDED.metadata
    WHERE vendor_probe_state.observed_at <= EXCLUDED.observed_at
    RETURNING *;
$$;

CREATE OR REPLACE FUNCTION record_vendor_rate_limit(
    p_observation_id TEXT,
    p_agent_id TEXT,
    p_scope TEXT,
    p_model TEXT,
    p_reason TEXT,
    p_source_agent_id TEXT,
    p_observed_at TIMESTAMPTZ,
    p_reset_at TIMESTAMPTZ,
    p_payload_hash TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS TABLE(write_status TEXT, normalized_reset_at TIMESTAMPTZ)
LANGUAGE sql AS $$
    WITH inserted AS (
        INSERT INTO vendor_rate_limits (
            observation_id, agent_id, scope, model, reason, source_agent_id,
            observed_at, reset_at, payload_hash, metadata
        ) VALUES (
            p_observation_id, p_agent_id, p_scope, p_model, p_reason, p_source_agent_id,
            p_observed_at, p_reset_at, p_payload_hash, p_metadata
        )
        ON CONFLICT (observation_id) DO NOTHING
        RETURNING payload_hash, reset_at
    )
    SELECT 'accepted', reset_at FROM inserted
    UNION ALL
    SELECT
        CASE WHEN existing.payload_hash = p_payload_hash THEN 'duplicate' ELSE 'conflict' END,
        existing.reset_at
    FROM vendor_rate_limits AS existing
    WHERE existing.observation_id = p_observation_id
      AND NOT EXISTS (SELECT 1 FROM inserted);
$$;

CREATE OR REPLACE FUNCTION compact_vendor_rate_limits(p_cutoff TIMESTAMPTZ)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM vendor_rate_limits WHERE reset_at <= p_cutoff;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;
