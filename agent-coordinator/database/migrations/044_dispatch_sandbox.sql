-- Migration 044: exact-agent sandbox policy export and durable execution audit
-- Dependencies: 007_agent_profiles.sql, 009_network_policies.sql,
--               018_agent_profile_assignments.sql

ALTER TABLE network_policies
    ADD COLUMN IF NOT EXISTS destination_kind TEXT,
    ADD COLUMN IF NOT EXISTS destination_pattern TEXT,
    ADD COLUMN IF NOT EXISTS port INTEGER,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE network_policies
SET destination_kind = CASE
        WHEN domain_pattern ~ '^\[[0-9A-Fa-f:]+\]$' THEN 'ipv6'
        WHEN domain_pattern ~ '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' THEN 'ipv4'
        ELSE 'dns'
    END,
    destination_pattern = lower(domain_pattern),
    updated_at = COALESCE(updated_at, created_at)
WHERE destination_kind IS NULL
   OR destination_pattern IS NULL
   OR updated_at IS NULL;

ALTER TABLE network_policies
    ALTER COLUMN destination_kind SET DEFAULT 'dns',
    ALTER COLUMN destination_kind SET NOT NULL,
    ALTER COLUMN destination_pattern SET NOT NULL,
    ALTER COLUMN updated_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL;

CREATE OR REPLACE FUNCTION valid_network_destination(p_kind TEXT, p_pattern TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_host TEXT;
BEGIN
    IF p_kind = 'dns' THEN
        RETURN p_pattern ~ '^(\*\.)?([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$'
           AND p_pattern !~ '^\*\.[^.]+$';
    ELSIF p_kind = 'ipv4' THEN
        RETURN family(p_pattern::inet) = 4 AND host(p_pattern::inet) = p_pattern;
    ELSIF p_kind = 'ipv6' THEN
        IF p_pattern !~ '^\[[0-9A-Fa-f:]+\]$' THEN
            RETURN false;
        END IF;
        v_host := substring(p_pattern FROM 2 FOR char_length(p_pattern) - 2);
        RETURN family(v_host::inet) = 6;
    END IF;
    RETURN false;
EXCEPTION WHEN OTHERS THEN
    RETURN false;
END;
$$;

ALTER TABLE network_policies DROP CONSTRAINT IF EXISTS network_policies_action_check;
ALTER TABLE network_policies ADD CONSTRAINT network_policies_action_check
    CHECK (action IN ('allow', 'deny')) NOT VALID;
ALTER TABLE network_policies DROP CONSTRAINT IF EXISTS network_policies_destination_check;
ALTER TABLE network_policies ADD CONSTRAINT network_policies_destination_check
    CHECK (valid_network_destination(destination_kind, destination_pattern)) NOT VALID;
ALTER TABLE network_policies DROP CONSTRAINT IF EXISTS network_policies_port_check;
ALTER TABLE network_policies ADD CONSTRAINT network_policies_port_check
    CHECK (port IS NULL OR port BETWEEN 1 AND 65535) NOT VALID;

CREATE OR REPLACE FUNCTION set_network_policy_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- Keep replay of pre-044 migrations and legacy writers compatible while
    -- ensuring the new typed columns are populated before constraints run.
    IF NEW.destination_pattern IS NULL THEN
        NEW.destination_pattern := lower(NEW.domain_pattern);
        NEW.destination_kind := CASE
            WHEN NEW.domain_pattern ~ '^\[[0-9A-Fa-f:]+\]$' THEN 'ipv6'
            WHEN NEW.domain_pattern ~ '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' THEN 'ipv4'
            ELSE 'dns'
        END;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS network_policies_updated_at ON network_policies;
CREATE TRIGGER network_policies_updated_at
BEFORE INSERT OR UPDATE ON network_policies
FOR EACH ROW EXECUTE FUNCTION set_network_policy_updated_at();

CREATE OR REPLACE FUNCTION export_network_policy(p_agent_id TEXT)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_profile_id UUID;
    v_profile_enabled BOOLEAN;
    v_known BOOLEAN;
    v_invalid BOOLEAN;
    v_rules JSONB;
    v_count INTEGER;
    v_max_updated TIMESTAMPTZ;
    v_revision TEXT;
BEGIN
    SELECT a.profile_id, p.enabled
      INTO v_profile_id, v_profile_enabled
      FROM agent_profile_assignments a
      JOIN agent_profiles p ON p.id = a.profile_id
     WHERE a.agent_id = p_agent_id;

    IF v_profile_id IS NULL THEN
        SELECT EXISTS(SELECT 1 FROM agent_sessions s WHERE s.agent_id = p_agent_id)
          INTO v_known;
        RETURN jsonb_build_object(
            'success', false,
            'reason', CASE WHEN v_known THEN 'agent_unassigned' ELSE 'agent_not_found' END
        );
    END IF;
    IF NOT v_profile_enabled THEN
        RETURN jsonb_build_object('success', false, 'reason', 'profile_disabled');
    END IF;

    SELECT EXISTS(
        SELECT 1 FROM network_policies np
         WHERE np.enabled
           AND (np.profile_id = v_profile_id OR np.profile_id IS NULL)
           AND (
               np.action NOT IN ('allow', 'deny')
               OR np.priority IS NULL
               OR np.updated_at IS NULL
               OR NOT valid_network_destination(np.destination_kind, np.destination_pattern)
               OR (np.port IS NOT NULL AND np.port NOT BETWEEN 1 AND 65535)
           )
    ) INTO v_invalid;
    IF v_invalid THEN
        RETURN jsonb_build_object('success', false, 'reason', 'invalid_policy');
    END IF;

    SELECT COALESCE(
               jsonb_agg(
                   jsonb_build_object(
                       'destination_kind', destination_kind,
                       'destination_pattern', destination_pattern,
                       'port', port,
                       'action', action,
                       'priority', priority,
                       'scope', CASE WHEN profile_id IS NULL THEN 'global' ELSE 'agent_profile' END,
                       'policy_id', id::text
                   ) ORDER BY
                       CASE WHEN profile_id IS NULL THEN 1 ELSE 0 END,
                       priority ASC,
                       CASE WHEN action = 'deny' THEN 0 ELSE 1 END,
                       id ASC
               ),
               '[]'::jsonb
           ),
           count(*)::integer,
           max(updated_at)
      INTO v_rules, v_count, v_max_updated
      FROM network_policies
     WHERE enabled
       AND (profile_id = v_profile_id OR profile_id IS NULL);

    v_revision := CASE
        WHEN v_count = 0 THEN 'v1:none:0'
        ELSE 'v1:' || to_char(v_max_updated AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') || ':' || v_count::text
    END;
    RETURN jsonb_build_object(
        'schema_version', 1,
        'agent_id', p_agent_id,
        'default_action', 'deny',
        'rules', v_rules,
        'policy_revision', v_revision
    );
END;
$$;

CREATE TABLE IF NOT EXISTS sandbox_execution_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL UNIQUE,
    actor_agent_id TEXT NOT NULL,
    target_agent_id TEXT NOT NULL,
    event JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE sandbox_execution_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sandbox_execution_events_read ON sandbox_execution_events;
CREATE POLICY sandbox_execution_events_read ON sandbox_execution_events
    FOR SELECT USING (true);
DROP POLICY IF EXISTS sandbox_execution_events_write ON sandbox_execution_events;
CREATE POLICY sandbox_execution_events_write ON sandbox_execution_events
    FOR ALL USING (current_setting('role') = 'service_role');

CREATE OR REPLACE FUNCTION record_sandbox_execution_event(
    p_actor_agent_id TEXT,
    p_event JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_id UUID;
    v_inserted INTEGER;
    v_allowed_keys TEXT[] := ARRAY[
        'schema_version','event_id','context_source','decision_id','item_id','phase','attempt',
        'dispatch_work_id','routing_context_digest','workspace_content_digest','agent_id',
        'vendor_type','policy_vendor','catalog_vendor','assignment_location','execution_location',
        'enforcement_scope','write_capable','dispatch_mode','model','endpoint_kind','endpoint_digest',
        'requested_isolation','sandbox_applied','backend','runtime_version','platform',
        'preflight_status','policy_revision','policy_digest','settings_digest','worktree_root',
        'executable_paths','environment_keys','degradation_reason','cleanup_status',
        'cleanup_residual_paths'
    ];
BEGIN
    IF p_actor_agent_id IS NULL OR p_actor_agent_id = '' OR jsonb_typeof(p_event) <> 'object'
       OR NOT (p_event ?& v_allowed_keys)
       OR EXISTS (
           SELECT 1
             FROM jsonb_object_keys(p_event) AS fields(key)
            WHERE NOT (fields.key = ANY(v_allowed_keys))
       )
       OR p_event->>'agent_id' IS NULL
       OR p_event->>'requested_isolation' <> 'sandbox'
       OR p_event->>'execution_location' <> 'local'
    THEN
        RAISE EXCEPTION 'invalid sandbox execution event' USING ERRCODE = '22023';
    END IF;

    INSERT INTO sandbox_execution_events(event_id, actor_agent_id, target_agent_id, event)
    VALUES ((p_event->>'event_id')::uuid, p_actor_agent_id, p_event->>'agent_id', p_event)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING id INTO v_id;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    IF v_inserted = 0 THEN
        SELECT id INTO v_id FROM sandbox_execution_events
         WHERE event_id = (p_event->>'event_id')::uuid;
    END IF;
    RETURN jsonb_build_object(
        'success', true,
        'event_id', p_event->>'event_id',
        'audit_entry_id', v_id::text,
        'replayed', v_inserted = 0
    );
END;
$$;
