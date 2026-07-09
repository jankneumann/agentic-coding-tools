# Design: add-adaptive-model-router

Selected approach: **A — coordinator-native selection service**. This document records the
load-bearing decisions; task and spec artifacts reference decisions by ID (D1…D12).

## D1 — Placement: coordinator owns decision + data; skills own execution

The catalog, signal ledger, posteriors, and `select_model_for_task` resolver live in the
coordinator (Postgres + FastAPI HTTP + MCP tool). Skills (`review_dispatcher.py`, `policy.py`,
autopilot) call the resolver and execute dispatch. Rationale: fleet-wide calibration requires
shared durable state; cloud agents have HTTP-only access; matches the Execution → Coordination →
Trust → Governance layering. Rejected: file-based skills-layer state (per-machine, racy — see
proposal Approach B).

## D2 — Fallback: static tiers remain the degraded path (feature flag)

`ROUTING_ADAPTIVE` (env/config, default `off` until validated) gates the new resolver. When off,
or when the resolver errors/times out (>2s), callers use today's
`resolve_archetype_for_phase()`/`resolve_model()` static tier path unchanged. Migrations are
additive-only. This is the rollback plan for the BREAKING change.

## D3 — Scoring: transparent linear utility, not a bandit policy (yet)

`score(model, task) = w_q · quality(model, task) − w_c · norm_cost(model, task) − w_l · norm_latency(model)`
where `quality = blend(benchmark_prior, task_type_posterior, confidence_weight)`.

**Cost term (amended 2026-07-09, Databricks benchmark insight)**: `norm_cost` is the
**success-adjusted observed cost-per-completed-task** posterior
(`observed_cost_usd / success_rate`, pricing in retries) for the `(model, task_type)` pair once
its sample size clears the confidence threshold; catalog per-Mtok pricing is only the cost
*prior* for unsampled pairs. Per-token price is a demonstrably poor proxy — Databricks measured
Sonnet 5 at ~1.7× cheaper per token than Opus 4.8 yet *more expensive per completed task*
($2.09 vs $1.94) at lower completion (81% vs 87%). Weights
`(w_q, w_c, w_l)` come from a named **objective profile** (`quality-first`, `balanced`,
`cost-first`, `resilience`) selectable per archetype/phase and overridable per call. Exploration
is epsilon-greedy on top of the ranking (D6), not a full bandit — decayed-average posteriors with
a confidence weight give most of the benefit without opaque state. Every decision emits a
provenance record (D8) so a future bandit can be trained offline.

## D4 — Catalog refresh: standing API key, not the MCP OAuth key

The OpenRouter MCP server's OAuth flow mints 7-day, $10-capped keys — fine for interactive
dev, wrong for a scheduled job. The coordinator's catalog refresher calls the OpenRouter REST API
(`/models`, endpoints/pricing) directly with a standing key from OpenBao/env
(`OPENROUTER_API_KEY`), on `WatchdogService` cadence (default 6h). Benchmark/ranking data
(Artificial Analysis scores, daily rankings) is ingested from the same refresher where the API
exposes it. The MCP server is additionally registered in `.mcp.json` as a **dev-time** tool for
interactive model exploration; production routing never calls MCP.

## D5 — Local endpoints: same catalog rows, health-probed

`agents.yaml` gains `endpoint_kind: local|openrouter|vendor-sdk|vendor-cli` and optional
`base_url`. Local (Ollama/vLLM) endpoints register catalog rows with `price ≈ 0`; a health probe
(same watchdog) marks availability and measures latency; quality priors are seeded via a one-shot
gen-eval calibration suite (task-type-representative prompts) rather than public benchmarks, since
local deployments vary (quantization, context limits).

## D6 — Exploration: explicit dual-ceiling budget

Exploration = deliberately selecting a lower-ranked candidate to gather posterior data. Enforced
by policy with two ceilings: `exploration_pct` (share of eligible tasks, default 10%) and
`exploration_monthly_usd` (hard cap on metered spend attributable to exploration). Premium-archetype
phases are exploration-ineligible by default (configurable). Exhausted budget ⇒ pure exploitation.
Every exploration decision is flagged in provenance so failures don't pollute exploitation
posteriors' interpretation.

## D7 — Spend governance: monthly ceiling on metered dispatch

A `routing_spend_ledger` accrues actual metered cost (OpenRouter reconciled via `generation-get`;
vendor SDKs via token counts × price table). Cedar policy denies metered dispatch when the monthly
ceiling (`ROUTING_MONTHLY_CEILING_USD`) would be exceeded; router then falls back to
subscription/local candidates. Metered-counterfactual baseline (absorbed from the arbitrage
instrument) is computed for *all* work units regardless of dispatch path — it is the savings
metric and economic tripwire input.

## D8 — Absorbed signal layer: events on audit_log + OTel, interpretations in Postgres tables

Signal *events* (throttles, enforcement, canary results, ToS diffs, routing decisions) ride the
existing `audit_log` with new `operation` types plus an OTel `coordinator.signal` meter with
`vendor/model/modality/archetype` labels. *Interpretive* state (catalog, posteriors, spend ledger,
decision provenance) gets dedicated tables (`model_catalog`, `model_posteriors`,
`routing_decisions`, `routing_spend_ledger`). This preserves the arbitrage instrument's hybrid
placement decision. `LearningEntry.vendor_notes` / `VendorSwitch` / `checkpoint.vendor_state`
remain the roadmap-workspace write path; the feedback aggregator (D9) is what promotes them into
posteriors.

## D9 — Feedback aggregation: decayed averages with source weights

A coordinator job folds four sources into `model_posteriors` keyed
`(model_id, task_type, metric)`. Source weights (amended 2026-07-09): **deterministic
verification outcomes rank above LLM-judged scores** — Databricks found LLM judging "rewards
sounding right over being right", so held-out-test/validation/CI outcomes from
`VendorSwitch`/`vendor_notes` weigh 1.0 (verified), gen-eval scores weigh 0.7 (their
`semantic_judge` component is an LLM judge; gen-eval's deterministic metric checks may claim
0.9 when separable), `memory_procedural` success/failure counts 0.5 (coarse), and struggle
signals from collect-transcripts triage 0.3 (inferred). Exponential decay (half-life 30 days) keeps posteriors current; a
`sample_size`-driven confidence weight controls the prior/posterior blend in D3. Task types
initially = archetype × phase-signal bucket (e.g. `implementer/high-complexity`).

## D10 — Dispatch adapter: one OpenAI-compatible adapter for OpenRouter + local

`review_dispatcher.py` gains `OpenAICompatAdapter(base_url, api_key, model)` used for
`endpoint_kind ∈ {openrouter, local}`. OpenRouter calls set attribution headers and record
generation IDs for D7 reconciliation. Existing CLI (tier-1) and vendor-SDK (tier-2) adapters are
untouched; the new adapter is tier-2.5 in discovery order. Hard constraints (Cedar): vendor
role/modality eligibility (Claude subscription = programmatic-ineligible), data residency, and
capability floors are evaluated *before* scoring — infeasible candidates never reach the ranker.

## D11 — Tripwires and probes (absorbed, slimmed)

Watchdog probes: **ToS-diff monitor** (fetch+hash automation-clause URLs; on change → freeze
vendor dispatch pending operator ack) and **model canary** (fixed prompt per model, fingerprint
drift → invalidate that model's posteriors/priors). Tripwires additionally: economic kill
(realized savings < maintenance threshold → alert + suggest `ROUTING_ADAPTIVE=off`) and
integration-cost signal (deferred to a report, not an automatic action, in this slice).

## D12 — Dashboard: extend kanban-viz pattern, read coordinator API only

`apps/usage-viz` (React + TS + Vite, Bearer auth, SSE/poll fallback — copied conventions from
`apps/kanban-viz`) renders per-vendor/model token+spend, counterfactual savings, posterior
scoreboard (success-criterion c is satisfied by the scoreboard view), and exploration budget
burn-down. **Headline comparison metric (amended 2026-07-09): cost-per-completed-task per
model×task-type — not $/Mtok**, so the UI surfaces the metric the router optimizes rather than
the per-token price that inverts real rankings. No SQLite, no transcript parsing in v1: data comes from the router ledger tables
(supersedes `usage-stats-multi-model`'s local-parsing design; its transcript-parsing idea is
recorded as a deferred task for backfilling history).

## Task-sizing notes

The only L-sized work is the coordinator catalog+ledger package (`wp-db-catalog`); it decomposes
internally as migrations → catalog service → refresher → probes and is flagged rather than split
further because the pieces share one schema review. Everything else is M or below.

## Absorption mechanics

`cross-vendor-arbitrage-instrument` and `usage-stats-multi-model` are archived (not deleted) with
`superseded-by: add-adaptive-model-router` notes in their proposal headers; their unimplemented
task lists were mined for requirements now expressed in this change's specs. No code exists under
either change, so no code migration is needed.
