-- Contract: usage statistics schema.
-- Realized as agent-coordinator/database/migrations/026_usage_stats.sql.
-- Style mirrors existing numbered migrations (IF NOT EXISTS, explicit indexes,
-- coordinator_notify trigger for SSE).

CREATE TABLE IF NOT EXISTS usage_records (
    id                    BIGSERIAL PRIMARY KEY,
    ts                    TIMESTAMPTZ NOT NULL,
    vendor                TEXT        NOT NULL,
    model                 TEXT        NOT NULL,
    input_tokens          BIGINT      NOT NULL DEFAULT 0,
    output_tokens         BIGINT      NOT NULL DEFAULT 0,
    cache_creation_tokens BIGINT      NOT NULL DEFAULT 0,
    cache_read_tokens     BIGINT      NOT NULL DEFAULT 0,
    cost_usd              NUMERIC(12,6),            -- NULL when model price unknown
    session_id            TEXT        NOT NULL,
    project               TEXT,                     -- full granularity (no redaction)
    principal             TEXT,                     -- fleet attribution
    agent_id              TEXT,
    host                  TEXT,
    record_hash           TEXT        NOT NULL,     -- dedupe key component
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Idempotency: a logical usage record is unique per vendor+session+hash.
    CONSTRAINT uq_usage_record UNIQUE (vendor, session_id, record_hash)
);

CREATE INDEX IF NOT EXISTS idx_usage_records_ts       ON usage_records (ts);
CREATE INDEX IF NOT EXISTS idx_usage_records_vendor   ON usage_records (vendor);
CREATE INDEX IF NOT EXISTS idx_usage_records_model    ON usage_records (model);
CREATE INDEX IF NOT EXISTS idx_usage_records_principal ON usage_records (principal);
-- Daily rollup support: bucketed scans by (vendor, day).
CREATE INDEX IF NOT EXISTS idx_usage_records_vendor_ts ON usage_records (vendor, ts);

-- Per-file incremental ingestion watermark (replaces claude-usage's mtime map).
CREATE TABLE IF NOT EXISTS usage_ingest_state (
    file_path     TEXT        PRIMARY KEY,
    vendor        TEXT        NOT NULL,
    last_mtime    DOUBLE PRECISION NOT NULL,   -- source file mtime (epoch seconds)
    byte_offset   BIGINT      NOT NULL DEFAULT 0,
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
