-- Contract: model usage ledger schema.
-- Realized as agent-coordinator/database/migrations/037_model_usage_ledger.sql.
-- Style mirrors existing numbered migrations (IF NOT EXISTS, explicit indexes).
-- Carries forward usage_records / usage_ingest_state from the superseded
-- usage-stats-multi-model change, extended per design D2, D3, D5, D6, D9.

-- One row per vendor API call (assistant message). D3.
CREATE TABLE IF NOT EXISTS usage_records (
    id                    BIGSERIAL PRIMARY KEY,
    ts                    TIMESTAMPTZ NOT NULL,
    vendor                TEXT        NOT NULL,
    model                 TEXT        NOT NULL,        -- vendor identifier as observed
    effort                TEXT,                        -- harness-reported reasoning level
    input_tokens          BIGINT      NOT NULL DEFAULT 0,
    output_tokens         BIGINT      NOT NULL DEFAULT 0,
    cache_creation_tokens BIGINT      NOT NULL DEFAULT 0,
    cache_read_tokens     BIGINT      NOT NULL DEFAULT 0,
    thinking_tokens       BIGINT,                      -- NULL when vendor does not report
    cost_usd              NUMERIC(12,6),               -- NULL when no price (D5)
    cost_reason           TEXT,                        -- 'no_price' when cost_usd IS NULL
    pricing_version       TEXT,
    estimated             BOOLEAN,
    vendor_cost_usd       NUMERIC(12,6),               -- vendor-reported, e.g. grok total_cost_usd
    session_id            TEXT        NOT NULL,
    agent_id              TEXT,                        -- sidechain sub-agent id, NULL for parent (D2)
    parent_session_id     TEXT,
    project               TEXT,
    principal             TEXT,
    host                  TEXT,
    git_branch            TEXT,
    message_id            TEXT,
    record_hash           TEXT        NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_usage_record UNIQUE (vendor, session_id, record_hash),
    -- Cost provenance (D5): a priced row must say which table priced it, and must be
    -- stamped estimated = true.
    --
    -- `estimated IS NOT NULL` was too weak: it admitted a priced row with estimated =
    -- false, which contradicts D5 and the usage-accounting contract (every calculated
    -- cost is an estimate, since it is derived from a price table rather than billed),
    -- and produces a row that cannot satisfy the OpenAPI response schema's `const: true`
    -- -- a database state with no valid API representation.
    CONSTRAINT ck_usage_cost_provenance CHECK (
        cost_usd IS NULL OR (pricing_version IS NOT NULL AND estimated IS TRUE)
    ),
    CONSTRAINT ck_usage_cost_reason CHECK (
        cost_usd IS NOT NULL OR cost_reason IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_usage_records_ts            ON usage_records (ts);
CREATE INDEX IF NOT EXISTS idx_usage_records_vendor_ts     ON usage_records (vendor, ts);
CREATE INDEX IF NOT EXISTS idx_usage_records_model         ON usage_records (model);
CREATE INDEX IF NOT EXISTS idx_usage_records_session_agent ON usage_records (session_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_usage_records_principal     ON usage_records (principal);

-- One row per autopilot phase dispatch (intent). D2.
CREATE TABLE IF NOT EXISTS dispatch_records (
    dispatch_id        TEXT        PRIMARY KEY,
    change_id          TEXT        NOT NULL,
    phase              TEXT        NOT NULL,
    archetype          TEXT,
    intended_tier      TEXT,
    intended_model     TEXT        NOT NULL,
    intended_thinking  TEXT,
    provider           TEXT,
    signals            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    override_source    TEXT,                          -- NULL | 'env' | 'config'
    session_id         TEXT        NOT NULL,          -- orchestrator session
    agent_id           TEXT,                          -- patched on the adapter RETURN path
                                                      -- (apply-outcome), never in
                                                      -- build_phase_dispatch_kwargs, which runs
                                                      -- before the adapter and cannot see its result
    -- 'dispatched' rows join to usage on (session_id, agent_id) and are flagged unattributed
    -- when nothing matches. 'state_only' rows (INIT, SUBMIT_PR) never invoke a sub-agent, so
    -- their agent_id is NULL by design and they MUST be excluded from mismatch accounting --
    -- SQL NULLs never match, so counting them would report the same three failures forever.
    record_kind        TEXT        NOT NULL DEFAULT 'dispatched'
                       CHECK (record_kind IN ('dispatched', 'state_only')),
    transcript_path    TEXT,
    dispatched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dispatch_records_change_phase  ON dispatch_records (change_id, phase);
CREATE INDEX IF NOT EXISTS idx_dispatch_records_session_agent ON dispatch_records (session_id, agent_id);

-- Sanitized normalized transcript events, 90-day retention. D6.
CREATE TABLE IF NOT EXISTS transcript_events (
    id                 BIGSERIAL PRIMARY KEY,
    ts                 TIMESTAMPTZ NOT NULL,
    vendor             TEXT        NOT NULL,
    session_id         TEXT        NOT NULL,
    agent_id           TEXT,
    parent_session_id  TEXT,
    event_type         TEXT        NOT NULL,          -- user | assistant | tool_call | tool_result | system
    schema_version     TEXT        NOT NULL,
    event              JSONB       NOT NULL,          -- sanitized NormalizedEvent
    event_hash         TEXT        NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_transcript_event UNIQUE (vendor, session_id, event_hash)
);

CREATE INDEX IF NOT EXISTS idx_transcript_events_ts            ON transcript_events (ts);
CREATE INDEX IF NOT EXISTS idx_transcript_events_session_agent ON transcript_events (session_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_transcript_events_created       ON transcript_events (created_at);

-- Per-file incremental ingestion watermark. D7.
-- Per-file incremental read cursors. Unlike usage_records and dispatch_records, which are
-- retained forever by design (D6), these rows are pure bookkeeping and are keyed by (host,
-- file_path). Cloud sessions get a fresh ephemeral host per container, so every cloud run
-- leaves cursor rows that will never be read again. The retention job SHALL purge rows whose
-- last_seen_at is older than USAGE_INGEST_STATE_RETENTION_DAYS (default 30); losing a cursor
-- for a host that never returns costs nothing, and losing one for a host that does return
-- only re-reads that file from the start, which the record_hash dedup makes harmless.
CREATE TABLE IF NOT EXISTS usage_ingest_state (
    file_path     TEXT        NOT NULL,
    host          TEXT        NOT NULL,
    vendor        TEXT        NOT NULL,
    last_mtime    DOUBLE PRECISION NOT NULL,
    line_offset   BIGINT      NOT NULL DEFAULT 0,
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (host, file_path)
);

-- Archetype enum parity (D9): replace the CHECK from 026_add_gatekeeper_archetype.
ALTER TABLE agent_sessions DROP CONSTRAINT IF EXISTS agent_sessions_phase_archetype_check;
ALTER TABLE agent_sessions ADD CONSTRAINT agent_sessions_phase_archetype_check CHECK (
    phase_archetype IS NULL OR phase_archetype IN (
        'architect', 'analyst', 'implementer', 'validator', 'reviewer',
        'runner', 'documenter', 'supervisor', 'gatekeeper'
    )
);
