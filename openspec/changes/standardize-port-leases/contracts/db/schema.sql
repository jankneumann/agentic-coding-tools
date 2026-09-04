-- Contract: port_leases (agent-coordinator migration 036_port_leases.sql)
-- Design D2: same shape as file_locks (001_core_schema.sql). A row with a NULL
-- session_id and a non-NULL blocked_until is a blocked slot (design D6).

CREATE TABLE IF NOT EXISTS port_leases (
    slot                INTEGER      NOT NULL,
    session_id          TEXT         NULL,
    agent_id            TEXT         NULL,
    db_port             INTEGER      NOT NULL,
    rest_port           INTEGER      NOT NULL,
    realtime_port       INTEGER      NOT NULL,
    api_port            INTEGER      NOT NULL,
    ui_port             INTEGER      NOT NULL,
    compose_project_name TEXT        NULL,
    -- Host the lease was allocated from. Scopes POST /ports/reconcile: a report may only
    -- release or block leases carrying its own host_id. Unscoped, a cloud agent's report --
    -- legitimately empty, since it cannot see a local host's containers -- would release
    -- every local lease on every host once each aged past conflict_block_minutes.
    host_id             TEXT         NULL,
    isolation_provided  BOOLEAN      NOT NULL DEFAULT FALSE,
    allocated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ  NULL,
    blocked_until       TIMESTAMPTZ  NULL,
    block_reason        TEXT         NULL,
    metadata            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT port_leases_pkey PRIMARY KEY (slot),
    CONSTRAINT port_leases_session_unique UNIQUE (session_id),
    CONSTRAINT port_leases_state CHECK (
        (session_id IS NOT NULL AND expires_at IS NOT NULL AND blocked_until IS NULL)
        OR (session_id IS NULL AND blocked_until IS NOT NULL)
    ),
    CONSTRAINT port_leases_block_layout CHECK (
        rest_port = db_port + 1 AND realtime_port = db_port + 2
        AND api_port = db_port + 3 AND ui_port = db_port + 4
    )
);

CREATE INDEX IF NOT EXISTS idx_port_leases_expires_at   ON port_leases (expires_at);
CREATE INDEX IF NOT EXISTS idx_port_leases_agent_id     ON port_leases (agent_id);
CREATE INDEX IF NOT EXISTS idx_port_leases_blocked_until ON port_leases (blocked_until);

-- Session tie-in (design D3): agent_sessions gains the client-reported isolation flag.
ALTER TABLE agent_sessions
    ADD COLUMN IF NOT EXISTS isolation_provided BOOLEAN NOT NULL DEFAULT FALSE;

-- Reclaim leases held by a set of STALE SESSIONS. Returns the number of rows deleted.
--
-- Keyed on session_id, never agent_id. One agent_id routinely has several
-- concurrent sessions — a validate-feature sweep and an interactive stack, say —
-- and deleting by agent identity would reclaim the live session's block along
-- with the dead one's. The freed slot is then reallocated while the active
-- stack is still bound to it, producing exactly the collision this capability
-- exists to prevent, and violating the requirement that active agents are
-- unaffected by cleanup.
--
-- Callers (the stale-session sweeper) must therefore resolve stale SESSIONS
-- first and pass those ids; an agent_id is not a safe proxy for "this work is
-- finished".
CREATE OR REPLACE FUNCTION release_port_leases_for_sessions(p_session_ids TEXT[])
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    released INTEGER;
BEGIN
    DELETE FROM port_leases
    WHERE session_id = ANY (p_session_ids);
    GET DIAGNOSTICS released = ROW_COUNT;
    RETURN released;
END;
$$;
