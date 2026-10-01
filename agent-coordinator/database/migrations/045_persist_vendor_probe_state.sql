-- 045: persist_vendor_probe_state, a jsonb-returning twin of upsert_vendor_probe_state.
--
-- Issue #643. The Postgres client calls RPCs as `SELECT fn(...)` and registers
-- jsonb with a text codec. upsert_vendor_probe_state (041) returns
-- SETOF vendor_probe_state, a composite with a jsonb column (`metadata`), which
-- asyncpg then cannot decode ("text encoding of composite types is not
-- supported"). Every watchdog probe write failed, so production never recorded
-- a single vendor probe. Returning the upserted row as jsonb decodes through
-- the existing codec on both backends: the Postgres client yields a dict and
-- PostgREST a JSON object, both of which VendorRegistryService.persist_probe
-- accepts.
--
-- This is a NEW function rather than a changed return type on the 041 one.
-- A Docker-seeded database re-runs every migration on first boot, tolerating
-- only "already exists" errors. Re-running 041's CREATE OR REPLACE against a
-- function whose return type had changed would fail ("cannot change return
-- type"), and the coordinator would not boot. 041's function is left as it is
-- and is no longer called.
--
-- Semantics match 041 exactly, including the stale-observation guard: an older
-- observation updates nothing, and the function then returns NULL.

BEGIN;

CREATE OR REPLACE FUNCTION persist_vendor_probe_state(
    p_agent_id TEXT,
    p_observation_id TEXT,
    p_status TEXT,
    p_source_agent_id TEXT,
    p_reason TEXT,
    p_observed_at TIMESTAMPTZ,
    p_stale_after TIMESTAMPTZ,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS JSONB
LANGUAGE sql AS $$
    WITH upserted AS (
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
        RETURNING *
    )
    SELECT to_jsonb(upserted) FROM upserted;
$$;

COMMIT;
