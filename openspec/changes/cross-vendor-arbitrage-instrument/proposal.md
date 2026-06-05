# Proposal: Cross-Vendor Cost-Arbitrage Learning Instrument

**Change ID**: cross-vendor-arbitrage-instrument
**Status**: Draft
**Created**: 2026-06-05
**Author**: Claude

## Summary

Build an **instrumentation-first** learning instrument for cross-vendor agent routing. The system runs a deliberately simple static-priority router (cheap-tier-first, spill on rate-limit) on top of a rich, durable **signal layer** that continuously answers two questions: *is cost arbitrage across subsidised vendor subscriptions still paying?* and *when do the conditions that make it pay (ToS terms, quota economics, model quality) shift?*

The strategic premise: **the arbitrage savings are transient, but the instrumentation is the durable asset.** Subsidised subscription capacity is a perishable, capped, adversarially-defended resource; the cost edge it provides will erode. The signals we build to exploit it — and to detect its erosion — outlive the edge and remain valuable as vendor-landscape intelligence. We therefore treat the instrument as the deliverable and the router as a thin, kill-switchable consumer of it.

## Why

Three forces make this worth building now, and worth building *as an instrument*:

1. **The window is open but closing.** Multiple commercial vendors (Claude, Codex, Gemini) currently subsidise flat-rate subscriptions to capture developers. Short-term, routing work across these subscriptions — under each vendor's current terms — captures real savings. But the subsidy is customer-acquisition spend: temporary by design, and the exact automated/multi-account usage we exploit is what vendors most want to rate-limit and restrict. Capturing the value requires acting now; *keeping* it requires knowing the moment terms change.

2. **The constraints that shape routing are themselves moving inputs, not fixed assumptions.** Claude's subscription EULA forces it into a lead/interactive role (no programmatic calls without metered API); Codex/Gemini/opencode currently permit programmatic CLI use. These are not eternal truths — they are *inputs* to a routing decision that must be expressed as mutable policy (config, not hardcode) so the topology reorganises itself when a vendor tightens terms.

3. **We have no cost/quota visibility today.** The coordinator already records locks, queue, policy, and audit events, and the learning-log schema *defines* `cost_observed_usd` / `latency_observed_seconds` fields — but nothing populates them. We are flying blind on the single metric (metered-counterfactual minus actual spend) that tells us whether any of this pays. Without the instrument, the arbitrage is faith-based.

This change converts a one-time "should we do cost arbitrage?" decision into a **standing telemetry layer** that answers it continuously and timestamps the moment the answer flips.

## What Changes

Per the planning decisions (hybrid placement, full first slice, static-pricing cost model, new capability spec):

### 1. Signal schema — five families (durable substrate)
A versioned signal record covering: **(a) compliance surface** — ToS clause diffs + enforcement events (429 bodies, anomalous auth failures); **(b) cost/quota economics** — per-`(vendor, model, modality, archetype, work-unit)` token tracking + metered-counterfactual cost + throttle events logged with cumulative-usage-at-throttle to triangulate the invisible cap; **(c) quality/model drift** — review/consensus outcomes per `(vendor, model, archetype)` + model-canary fingerprints; **(d) integration/composition cost** attributed back to the routing decision that split a feature across vendors; **(e) decision provenance** — routing inputs (priors, quota state, constraints, objective weights), the chosen assignment, and realised outcome.

**Placement (hybrid):** append-only signal *events* ride the coordinator's `audit_log` (custom `operation` types) and OTel (`coordinator.signal` meter with `vendor`/`model`/`modality`/`archetype` labels); interpretive records (decision provenance, cost ledger) extend `roadmap-runtime` `LearningEntry.vendor_notes` and `checkpoint.vendor_state`.

### 2. Metered-counterfactual ledger (the load-bearing metric)
Every unit of work records what it *would* have cost on metered API. Cumulative `(metered_baseline − actual_spend)` is the one number that answers "is arbitrage worth it" — and the economic kill-signal when it crosses maintenance cost. **Cost source (decided):** a versioned, mutable per-vendor price table in config; token counts from CLI/SDK adapter responses where available, heuristic estimation (clearly labelled as estimate) where the CLI does not report usage.

### 3. Two scheduled active probes (turn invisible state observable)
- **ToS monitor** — fetch + hash/diff each vendor's automation-clause URL on a schedule; emit a compliance signal on change.
- **Model canary** — a tiny fixed prompt per model, response fingerprinted; alarm on drift to catch silent model swaps under fixed names.

**Placement:** both run on the coordinator's existing `WatchdogService` (`WATCHDOG_INTERVAL_SECONDS`); the network-touching ToS fetch may alternatively run as a GitHub Actions cron.

### 4. Static-priority router with hard/soft split (the dumb-on-purpose consumer)
- **Hard feasibility constraints** (Cedar): vendor role/modality eligibility — Claude = lead-eligible / programmatic-ineligible on subscription; Codex/Gemini/opencode = programmatic-eligible — plus data-residency and capability-floor. Implemented as Cedar `forbid()` policies + new `vendor`/`modality`/`data_residency` attributes on the Agent entity; vendor flags stored mutably in `agent_profiles.metadata` / `agents.yaml`.
- **Soft scoring** (skills): cheap-tier-first, spill on hard rate-limit, prefer cohesion (keep a work-package on one vendor unless the delta clears a switching penalty). Drives the existing `agents_config` / `review_dispatcher` dispatch adapters. No bandit, no temporal optimiser in this slice — deliberately.

### 5. Tripwires (posture flips that are themselves logged learnings)
ToS-diff → freeze dispatch to that vendor; enforcement-pattern → demote modality; realised-savings < maintenance → economic kill; canary-drift → invalidate that model's priors; integration-cost > routing-savings → collapse to one-vendor-per-feature.

### 6. Weekly landscape digest (the learning surface)
A generator that reads the signal substrate and emits a vendor-landscape report: utilisation vs inferred cap, cumulative $ saved vs metered baseline, ToS diffs, model drift, prior shifts, integration-cost verdict. This digest is the durable, vendor-independent IP.

### 7. New capability spec, coordinating with existing specs
A new `openspec/specs/cross-vendor-arbitrage` capability. It explicitly **fulfils** the `observability` spec's unimplemented cost requirement and **subsumes/feeds** the `symphony` roadmap's `token-rate-limit-and-run-accounting` item (cross-referenced, not duplicated). References `agent-archetypes` for model resolution and `roadmap-orchestration` for learning-log emission.

**Existing foundations**: `agent-coordinator/src/audit.py`, `src/telemetry.py`, `src/policy_engine.py` + `cedar/schema.cedarschema`, `src/watchdog.py`, `src/agents_config.py`; `skills/parallel-infrastructure/scripts/review_dispatcher.py`; `skills/roadmap-runtime/scripts/{models,learning,checkpoint}.py`; `openspec/schemas/learning-log.schema.json`, `checkpoint.schema.json`.

## Out of Scope (deferred to follow-ups)

- **Smart routing** — bandit/exploration, quota-aware temporal bin-packing, learned per-`(vendor, archetype)` quality priors. This slice ships *static* routing; the instrument is what later *earns* the smart router (only build it if the metered-baseline ledger says the margin justifies it).
- **Two-level orchestration** (Claude strategic lead delegating fan-out to a cheap programmatic tactical orchestrator) — a routing optimisation, deferred until the signal layer proves the quota pressure that motivates it.
- **Verifying vendor ToS claims** — the ToS monitor *detects change*; it does not adjudicate legality. The operator owns the compliance reading.

## Approaches Considered

### Approach A: Dedicated bounded instrument capability **(Recommended)**

A new, cohesive `cross-vendor-arbitrage` bounded context (a coordinator-side `arbitrage_signal` module + a `skills/vendor-arbitrage` skill for router/digest) that **owns** the signal schema, ledger, router, probes, and digest as one unit, and **consumes** coordinator primitives (audit_log, OTel, Cedar, WatchdogService) and roadmap-runtime storage without reinventing them.

- **Pros**
  - Matches the kill-switch principle exactly: the entire instrument is one removable unit with a single feature flag; disabling it leaves the coordinator and skills untouched.
  - Internally consistent with the "new capability spec" decision — one bounded capability, one spec, one owner.
  - Clear seams for the deferred smart-router: it slots in behind the same router interface without touching the signal layer.
- **Cons**
  - Introduces a new top-level component (a new skill + a new coordinator module), the largest new surface of the three.
  - Spans both codebases (coordinator + skills), so the work-package DAG must coordinate a contract boundary between them.
- **Effort**: L

### Approach B: Distributed extension-in-place

Push each concern into the nearest existing module — ledger fields into `roadmap-runtime` models, router into `agents_config`/dispatch, probes into `watchdog`, signals into `audit`, eligibility into Cedar — with **no** new bounded component, just additive requirements across existing spec surfaces.

- **Pros**
  - Smallest net-new surface area; maximal reuse; no new deploy/ownership unit.
  - Each piece lands in the module a maintainer already knows.
- **Cons**
  - The instrument becomes **diffuse** — there is no single thing to kill, flag, or remove, directly violating the kill-switchable principle that motivates the whole design.
  - Couples experimental, churn-prone arbitrage logic into stable core modules, raising their blast radius.
  - Conflicts with the "new capability spec" decision (the capability has no coherent home).
- **Effort**: M

### Approach C: Coordinator-only monolith

Implement everything — signals, ledger, router, probes, digest — as coordinator `src/` modules + dedicated DB tables; skills call it only over HTTP.

- **Pros**
  - Centralised aggregation and a single deploy surface; strongest cross-session/cross-agent consistency.
  - All state in Postgres, queryable in one place.
- **Cons**
  - Duplicates the `roadmap-runtime` ledger/learning concepts the codebase already has (the schema fields exist there today), creating two sources of truth for cost/decision data.
  - Embeds the transient, kill-switchable arbitrage logic into the core coordinator — the opposite of keeping it removable.
  - Heaviest migration footprint (new tables) for data that has existing homes.
- **Effort**: L

### Selected Approach

**Approach A — Dedicated bounded instrument capability** (approved at Gate 1, 2026-06-05).

Rationale: it is the only option that honours the governing principle — cost arbitrage is a *kill-switchable add-on, not a foundation*. A diffuse implementation (B) has no single kill switch; a coordinator monolith (C) embeds transient, churn-prone logic into the stable core and duplicates the roadmap-runtime ledger. Approach A pays a bounded up-front cost (a new skill + a new coordinator module behind a contract) to buy a clean removal seam, a single feature flag, and a slot-in point for the deferred smart router. No modifications requested to the approach as written.

Approaches B and C are retained above as the considered-and-rejected alternatives.
