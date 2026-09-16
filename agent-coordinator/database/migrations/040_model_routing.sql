-- 040: additive storage for adaptive model routing.

BEGIN;

CREATE TABLE IF NOT EXISTS model_catalog (
    id BIGSERIAL PRIMARY KEY,
    vendor TEXT NOT NULL,
    model TEXT NOT NULL,
    endpoint_kind TEXT NOT NULL CHECK (
        endpoint_kind IN ('vendor-cli', 'vendor-sdk', 'openrouter', 'local')
    ),
    base_url TEXT,
    prompt_usd_per_mtok NUMERIC(12,6),
    completion_usd_per_mtok NUMERIC(12,6),
    context_window INTEGER,
    benchmark_priors JSONB NOT NULL DEFAULT '{}'::jsonb,
    p50_latency_ms NUMERIC(10,2),
    available BOOLEAN NOT NULL DEFAULT TRUE,
    quota_headroom_pct NUMERIC(5,2),
    quota_reset_at TIMESTAMPTZ,
    quota_source TEXT,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (vendor, model, endpoint_kind)
);

CREATE INDEX IF NOT EXISTS idx_model_catalog_routable
    ON model_catalog (available, endpoint_kind, vendor, model);

CREATE TABLE IF NOT EXISTS model_posteriors (
    id BIGSERIAL PRIMARY KEY,
    catalog_id BIGINT NOT NULL REFERENCES model_catalog(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    metric TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    sample_size DOUBLE PRECISION NOT NULL DEFAULT 0,
    half_life_days INTEGER NOT NULL DEFAULT 30,
    low_confidence BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (catalog_id, task_type, metric)
);

CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    request JSONB NOT NULL,
    selected JSONB NOT NULL,
    alternatives JSONB NOT NULL DEFAULT '[]'::jsonb,
    excluded JSONB NOT NULL DEFAULT '[]'::jsonb,
    exploration BOOLEAN NOT NULL DEFAULT FALSE,
    fallback BOOLEAN NOT NULL DEFAULT FALSE,
    policy_version TEXT NOT NULL,
    budget_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome_ref TEXT
);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_created
    ON routing_decisions (created_at);

CREATE TABLE IF NOT EXISTS routing_spend_ledger (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decision_id UUID REFERENCES routing_decisions(decision_id),
    vendor TEXT NOT NULL,
    model TEXT NOT NULL,
    endpoint_kind TEXT NOT NULL,
    prompt_tokens BIGINT,
    completion_tokens BIGINT,
    tokens_estimated BOOLEAN NOT NULL DEFAULT FALSE,
    actual_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
    counterfactual_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
    exploration BOOLEAN NOT NULL DEFAULT FALSE,
    generation_id TEXT,
    work_unit_ref TEXT
);

CREATE INDEX IF NOT EXISTS idx_spend_ledger_month
    ON routing_spend_ledger (
        date_trunc('month', occurred_at AT TIME ZONE 'UTC'), endpoint_kind
    );

COMMIT;
