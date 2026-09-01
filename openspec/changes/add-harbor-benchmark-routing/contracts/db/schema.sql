-- Contract for migration 035_model_routing.sql
-- Derived from add-adaptive-model-router contracts/db/schema.sql; lands only the
-- two tables this change needs (design.md D3). routing_decisions and
-- routing_spend_ledger remain owned by add-adaptive-model-router.

CREATE TABLE IF NOT EXISTS model_catalog (
    id              BIGSERIAL PRIMARY KEY,
    vendor          TEXT        NOT NULL,
    model           TEXT        NOT NULL,
    thinking        TEXT        NOT NULL DEFAULT '',   -- '' = vendor default; distinct tiers are distinct rows
    endpoint_kind   TEXT        NOT NULL DEFAULT 'cli',
    benchmark_prior NUMERIC,                            -- blended 0..1 quality prior
    prior_source    TEXT,                               -- 'harbor-replay' | 'openrouter' | 'gen-eval' | ...
    prompt_usd_per_mtok     NUMERIC,
    completion_usd_per_mtok NUMERIC,
    available       BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT model_catalog_combo_uniq UNIQUE (vendor, model, thinking, endpoint_kind),
    CONSTRAINT prior_requires_source CHECK (benchmark_prior IS NULL OR prior_source IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS model_posteriors (
    id           BIGSERIAL PRIMARY KEY,
    catalog_id   BIGINT      NOT NULL REFERENCES model_catalog(id) ON DELETE CASCADE,
    task_type    TEXT        NOT NULL,                 -- package_kind vocabulary (design.md D7)
    metric       TEXT        NOT NULL,                 -- 'quality' | 'success_rate' | 'cost_per_task_usd' | 'latency_seconds'
    value        NUMERIC     NOT NULL,
    sample_size  INTEGER     NOT NULL DEFAULT 0,
    source       TEXT        NOT NULL,                 -- 'harbor-replay' for this change
    graded_by    TEXT        NOT NULL DEFAULT 'deterministic',  -- 'deterministic' | 'judge' | 'mixed'
    last_job_id  TEXT,                                 -- idempotency key for re-imports
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT model_posteriors_key_uniq UNIQUE (catalog_id, task_type, metric, source)
);

CREATE INDEX IF NOT EXISTS idx_model_catalog_vendor_model ON model_catalog (vendor, model);
CREATE INDEX IF NOT EXISTS idx_model_posteriors_task_type ON model_posteriors (task_type, metric);
