# Change: add-adaptive-model-router

**Status**: Draft
**Created**: 2026-07-08
**Author**: Claude (plan-feature, coordinated tier)
**Supersedes**: `cross-vendor-arbitrage-instrument` (absorbed), `usage-stats-multi-model` (absorbed)

## Why

Model/vendor selection today is static config (`agents.yaml` + `archetypes.yaml` tiers) with a
hardcoded cost stub (`skills/autopilot-roadmap/scripts/policy.py::_estimate_cost_delta`), so every
run either overpays a premium model for easy work or requires the operator to hand-pick vendors —
and nothing the fleet learns about model×task performance is retained. The OpenRouter MCP server
(live `models-list`, `benchmarks`, `rankings-daily`, `model-endpoints` pricing/latency) plus the
feedback plumbing this repo already defines but never populates (`LearningEntry.vendor_notes`,
`VendorSwitch` expected-vs-observed deltas, `memory_procedural` counters, gen-eval scores) make an
adaptive router buildable now: benchmark-calibrated priors, task-feedback posteriors, and
configurable cost/quality/resilience trade-offs, covering subscription CLIs, metered APIs
(including OpenRouter itself), and local endpoints (Ollama/vLLM).

**Latent intent (from discovery)**: automation of the model-choice decision and durable learning
about model×task fit are the primary goals; cost cutting and resilience are configurable
objectives, not fixed ones. Success after ~a month: (a) autopilot/quick-task runs complete with
no manual model picks, (b) local models absorb a meaningful share of economy-tier traffic.

## What Changes

- **New capability `model-routing`** owning the model catalog, scoring, and selection contract.
- **Model catalog + signal ledger in coordinator Postgres** (new migrations): per
  `(vendor, model, endpoint_kind, archetype/task-type)` rows carrying benchmark priors
  (Artificial Analysis scores, rankings), per-Mtok pricing, observed latency, and feedback
  posteriors. Absorbs the arbitrage instrument's five parts: signal schema + decision provenance,
  metered-counterfactual cost ledger, active probes (ToS-diff monitor, model canary), Cedar hard
  constraints (e.g. Claude subscription = programmatic-ineligible), and tripwires (vendor freeze,
  economic kill, prior invalidation on canary drift).
- **OpenRouter catalog refresher**: scheduled job (coordinator `WatchdogService`) pulling
  `models-list` / `model-endpoints` / `benchmarks` / `rankings-daily` via a standing OpenRouter
  API key (not the 7-day OAuth MCP key); local endpoints register into the same catalog via
  health probe.
- **`select_model_for_task` resolver** in `agent-coordinator/src/agents_config.py`, exposed as
  HTTP `POST /routing/select_model` and MCP tool alongside `resolve_for_phase`. Score =
  benchmark prior + task-type posterior − λ_cost·price − λ_latency·latency, with **configurable
  objective weights** (cost/quality/resilience profile) and an **explicit exploration budget knob**
  (percent-of-tasks and monthly-$ ceiling, policy-enforced).
- **OpenAI-compatible `base_url` dispatch adapter** in
  `skills/parallel-infrastructure/scripts/review_dispatcher.py` covering OpenRouter (metered,
  under a **monthly spend ceiling**) and local Ollama/vLLM endpoints from day one.
- **Replace the cost stub**: `policy.py::_estimate_cost_delta` and `evaluate_policy` read real
  catalog pricing; `generation-get` reconciles actual OpenRouter spend.
- **Feedback aggregator** rolling `vendor_notes`, `VendorSwitch` deltas, gen-eval scores, and
  `memory_procedural` counts into per-(model, task-type) posteriors (decayed averages first).
- **Usage/cost dashboard** (absorbs `usage-stats-multi-model`): coordinator-Postgres-backed
  per-vendor/model token+spend view reusing the `apps/kanban-viz` React/Vite pattern, reading the
  router's ledger instead of a separate SQLite store.
- **BREAKING**: `resolve_model()` callers (autopilot phase dispatch) route through the new
  resolver when the routing feature flag is on; `agents.yaml` gains `endpoint_kind`/`base_url`
  fields. *Rollback plan*: feature flag `ROUTING_ADAPTIVE=off` reverts to static archetype tier
  resolution (existing behavior preserved as the fallback path); migrations are additive-only.
- **Archive the two absorbed draft changes** with pointers to this change.

## Approaches Considered

### Approach A — Coordinator-native selection service (full absorption) — **Recommended**

Catalog, ledger, posteriors, and the resolver live in the coordinator (Postgres + FastAPI/MCP);
skills stay the dispatch/execution layer; dashboard reads coordinator API.

- **Pros**: single fleet-wide source of truth (calibration requires cross-machine aggregation —
  both absorbed proposals independently reached the same conclusion); works for cloud (HTTP) and
  local (MCP) agents; matches the layered architecture (decision = Coordination, hard constraints
  = Governance/Cedar, dispatch = Execution); one coherent home for the absorbed schemas.
- **Cons**: largest scope — needs migrations, watchdog jobs, API surface; coordinator becomes a
  routing dependency (mitigated: resolver failure falls back to static tiers).
- **Effort**: L (decomposed into parallel work packages below).

### Approach B — Skills-layer router with file-based state

Extend `policy.py`/`parallel-infrastructure` directly; catalog and posteriors as versioned
YAML/JSON in the repo or roadmap workspace; OpenRouter queried at dispatch time.

- **Pros**: no coordinator changes; incremental; works with coordinator down.
- **Cons**: per-machine state defeats fleet calibration (the learning goal); racy under parallel
  agents; contradicts the absorbed instrument's placement decision (audit_log + OTel); dispatch-time
  OpenRouter calls add latency and a network dependency to every routing decision.
- **Effort**: M.

### Approach C — External gateway (LiteLLM-style proxy) as the router

Point all SDK dispatch at a self-hosted LiteLLM (or OpenRouter directly); routing, fallbacks, and
budgets configured in the gateway; coordinator only records outcomes.

- **Pros**: battle-tested routing/budget/fallback machinery for free; `base_url` unification comes
  built-in; least custom code.
- **Cons**: cannot route CLI-subscription dispatch (Claude Code/Codex/Gemini CLIs — the majority
  of traffic and the entire arbitrage edge live outside any HTTP proxy); gateway config cannot
  consume task-specific feedback posteriors; new always-on infrastructure to operate; subscription
  EULA constraints can't be expressed as gateway config.
- **Effort**: M–L.

**Recommendation rationale**: A is the only approach that serves the stated latent intent
(fleet-wide learning + automation). B sacrifices the learning asset to per-machine state; C cannot
see the subscription-CLI traffic that dominates both volume and savings. A's main con (scope) is
manageable because the static-tier path remains the fallback and all schema work was already
designed in the absorbed proposals.

## Impact

| Capability (spec delta) | Nature |
|---|---|
| `model-routing` (**new**) | Catalog, resolver contract, exploration budget, tripwires, probes |
| `agent-coordinator` | New endpoints (`/routing/select_model`, catalog CRUD), migrations, watchdog jobs |
| `agent-archetypes` | Tier resolution delegates to router when flag on; `endpoint_kind` in aliases |
| `roadmap-orchestration` | `policy.py` cost model reads catalog; exploration budget enforcement |
| `observability` | Usage/cost dashboard (absorbed from `usage-stats-multi-model`) |

**Code**: `agent-coordinator/src/agents_config.py`, `src/coordination_api.py`, new
`src/model_routing/`, `database/migrations/00X_model_routing.sql`,
`skills/parallel-infrastructure/scripts/review_dispatcher.py`,
`skills/autopilot-roadmap/scripts/policy.py`, `skills/roadmap-runtime/scripts/learning.py`,
`apps/usage-viz/` (new, patterned on `apps/kanban-viz`), `.mcp.json` (OpenRouter MCP, dev-time),
`agents.yaml` / `archetypes.yaml` schema extensions.

**Architecture layers**: Execution (dispatch adapter), Coordination (catalog/resolver/ledger),
Trust (per-model reliability posteriors), Governance (Cedar hard constraints, spend ceilings,
tripwires).

**Conflicts**: `fix-autopilot-archetype-and-apply-outcome` touches archetype resolution — file-level
overlap in `agents_config.py`; sequence that fix first or rebase over it.
