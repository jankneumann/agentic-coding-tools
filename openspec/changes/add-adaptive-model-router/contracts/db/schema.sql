-- Model routing storage contract (additive-only migration; see design D2/D8).
-- Signal *events* ride the existing audit_log; these tables are interpretive state.

CREATE TABLE IF NOT EXISTS model_catalog (
    id                      BIGSERIAL PRIMARY KEY,
    vendor                  TEXT        NOT NULL,
    model                   TEXT        NOT NULL,
    endpoint_kind           TEXT        NOT NULL CHECK (endpoint_kind IN ('vendor-cli','vendor-sdk','openrouter','local')),
    base_url                TEXT,
    prompt_usd_per_mtok     NUMERIC(12,6),
    completion_usd_per_mtok NUMERIC(12,6),
    context_window          INTEGER,
    benchmark_priors        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    p50_latency_ms          NUMERIC(10,2),
    available               BOOLEAN     NOT NULL DEFAULT TRUE,
    refreshed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    stale                   BOOLEAN     NOT NULL DEFAULT FALSE,
    UNIQUE (vendor, model, endpoint_kind)
);

CREATE TABLE IF NOT EXISTS model_posteriors (
    id            BIGSERIAL PRIMARY KEY,
    catalog_id    BIGINT      NOT NULL REFERENCES model_catalog(id),
    task_type     TEXT        NOT NULL,
    metric        TEXT        NOT NULL,           -- quality | success_rate | latency_s | cost_usd
    value         DOUBLE PRECISION NOT NULL,
    sample_size   DOUBLE PRECISION NOT NULL DEFAULT 0,  -- decayed effective samples
    half_life_days INTEGER    NOT NULL DEFAULT 30,
    low_confidence BOOLEAN    NOT NULL DEFAULT FALSE,   -- set by canary drift (D11)
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (catalog_id, task_type, metric)
);

CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    request        JSONB       NOT NULL,           -- SelectModelRequest snapshot
    selected       JSONB       NOT NULL,           -- Candidate snapshot
    alternatives   JSONB       NOT NULL DEFAULT '[]'::jsonb,
    excluded       JSONB       NOT NULL DEFAULT '[]'::jsonb,  -- hard-constraint exclusions + reasons
    exploration    BOOLEAN     NOT NULL DEFAULT FALSE,
    fallback       BOOLEAN     NOT NULL DEFAULT FALSE,
    policy_version TEXT        NOT NULL,
    budget_state   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    outcome_ref    TEXT                                        -- feedback event id once realised
);
CREATE INDEX IF NOT EXISTS idx_routing_decisions_created ON routing_decisions (created_at);

CREATE TABLE IF NOT EXISTS routing_spend_ledger (
    id                  BIGSERIAL PRIMARY KEY,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    decision_id         UUID        REFERENCES routing_decisions(decision_id),
    vendor              TEXT        NOT NULL,
    model               TEXT        NOT NULL,
    endpoint_kind       TEXT        NOT NULL,
    prompt_tokens       BIGINT,
    completion_tokens   BIGINT,
    tokens_estimated    BOOLEAN     NOT NULL DEFAULT FALSE,   -- estimate labelling (spec model-routing.8)
    actual_usd          NUMERIC(12,6) NOT NULL DEFAULT 0,
    counterfactual_usd  NUMERIC(12,6) NOT NULL DEFAULT 0,
    exploration         BOOLEAN     NOT NULL DEFAULT FALSE,   -- attributes spend to exploration budget (D6)
    generation_id       TEXT,                                  -- OpenRouter generation-get reconciliation
    work_unit_ref       TEXT                                   -- change-id/package/task attribution
);
CREATE INDEX IF NOT EXISTS idx_spend_ledger_month ON routing_spend_ledger (date_trunc('month', occurred_at), endpoint_kind);
