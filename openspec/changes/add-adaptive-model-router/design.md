# Design: add-adaptive-model-router

Selected approach: **A — coordinator-native selection service**. This document records the
load-bearing decisions; task and spec artifacts reference decisions by ID (D1…D14).

## D1 — Placement: coordinator owns decision + data; skills own execution

The catalog, signal ledger, posteriors, and `select_model_for_task` resolver live in the
coordinator (Postgres + FastAPI HTTP + MCP tool). Skills (`review_dispatcher.py`, `policy.py`,
autopilot) call the resolver and execute dispatch. Rationale: fleet-wide calibration requires
shared durable state; cloud agents have HTTP-only access; matches the Execution → Coordination →
Trust → Governance layering. Rejected: file-based skills-layer state (per-machine, racy — see
proposal Approach B).

## D2 — Fallback: static tiers remain the degraded path (feature flag)

`ROUTING_ADAPTIVE` (env/config, default `off` until validated) gates the new resolver. When off,
or when the resolver errors/times out (>2s), callers use the same effective static tier behavior
through the model chains owned by `archetypes.yaml` (D14), never an ambient harness default or a
model copied from `agents.yaml`. Migrations are additive-only. This is the rollback plan for the
BREAKING change.

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

## D13 — Proactive quota headroom via quota-axi (optional signal adapter)

The router reads **proactive** subscription quota state — remaining window percentage and reset
time per provider — instead of only inferring caps reactively from 429 throttles (the arbitrage
instrument's cumulative-usage-at-throttle triangulation). Source: the `quota-axi` CLI
(https://github.com/kunchenguid/quota-axi, MIT), a read-only tool that reads local provider
credentials and calls first-party quota endpoints for Claude/Codex/Cursor/Copilot/Grok.

**Integration shape**: a worker-side quota reporter shells out to `npx -y quota-axi --json`,
normalizes results to a `cost_quota`-family signal, and feeds (a) a `quota_headroom_pct` /
`quota_reset_at` field on the catalog row (proactive feasibility), and (b) the resolver's
`resilience` objective (prefer models with headroom). **Off by default** behind
`ROUTING_QUOTA_PROBE` (Rule 4); degrades to reactive-only 429-triangulation when Node, local
credentials, or provider coverage are absent.

**Boundaries** (why this is safe): quota-axi is read-only ("it is data only") — it never routes,
proxies, or mutates, so it is purely an input with no overlap with the resolver. It does **not**
replace 429-triangulation: coverage excludes Gemini, OpenRouter, and local endpoints, so both
mechanisms coexist under one signal family. Because quota is per-account/per-machine, it runs
worker-side and reports into the coordinator via the existing signal path, not as a central poll.
Adopted as a pinned subprocess dependency, not vendored; if the dependency proves unstable the
fallback is to read the same first-party endpoints directly in Python for our vendor set.

## D14 — Harness mechanics and static model policy have separate authorities

`agents.yaml` owns agent identity, eligibility, transport, credentials, endpoint metadata, and
harness invocation mechanics. Invocation mechanics include `cli.command`, dispatch-mode flags,
prompt delivery, polling, SDK package/method/token limits, and the name of `model_flag`; they do
not include a model value. The schema rejects concrete CLI/SDK primary or fallback models.

`archetypes.yaml` is the sole curated static model-policy source. The canonical
`provider-model-map.schema.json` contract is versioned to v3 with the exact route shape
`routes[agent_id][dispatch_kind][tier]: ModelSpec[]`; v2 `providers` data is read only during
migration, the v3 writer emits only `routes`, and mixed v2/v3 documents are rejected. It maps
each dispatchable agent harness and dispatch kind (`cli` or `sdk`) to an ordered `ModelSpec`
chain per logical tier;
each chain item carries a concrete model and optional thinking level. A task/phase selects an
archetype, the archetype selects a tier, and the agent harness plus dispatch kind resolves that
tier to its chain. Dispatchable agents declare a non-empty archetype list, and cross-file
validation fails before dispatch when any eligible combination lacks a chain or an orphan harness
mapping exists. Python defaults contain structure only, never model IDs.

Migration is parity-gated. Task 4.7 characterizes every current CLI/SDK primary and fallback;
task 4.8 seeds those values into the new routes without changing effective selection or retry
order; task 4.9 switches all consumers only after parity passes, then removes the legacy
concrete model fields. Task 3.10 retains the legacy static path until that atomic cutover.

Adaptive resolution is scoped by `agent_id` and `dispatch_kind`. A dynamic candidate may
replace only the primary `ModelSpec`; the response carries its thinking level plus a
`capacity_fallbacks` chain formed from the same route's static `archetypes.yaml` chain with the
selected model removed to prevent a duplicate attempt.

Capacity errors consume only `capacity_fallbacks`; ranked adaptive alternatives remain
provenance and require a separate routing decision. When adaptive routing is disabled or
unavailable, the whole static chain is returned. CLI ambient defaults and implicit SDK defaults
are not valid fallback paths.

## Task-sizing notes

The two flagged L packages are coordinator catalog+ledger (`wp-db-catalog`) and the cross-layer
static model-policy migration (`wp-model-config-ownership`). Both decompose into M-or-smaller
tasks. The catalog package decomposes internally as migrations → catalog service → refresher →
probes and is flagged rather than split further because the pieces share one schema review.
Everything else is M or below.

## Absorption mechanics

`cross-vendor-arbitrage-instrument` and `usage-stats-multi-model` are archived (not deleted) with
`superseded-by: add-adaptive-model-router` notes in their proposal headers; their unimplemented
task lists were mined for requirements now expressed in this change's specs. No code exists under
either change, so no code migration is needed.
