# model-routing Specification

## Purpose

Adaptively select the model/vendor/endpoint for each unit of agent work by combining live
benchmark and pricing priors (OpenRouter catalog), task-specific feedback posteriors (fleet
learning), and configurable cost/quality/resilience objectives — under hard feasibility
constraints, explicit exploration and spend budgets, and a kill-switchable fallback to static
tier resolution. Absorbs the signal layer, counterfactual ledger, probes, hard constraints, and
tripwires designed in `cross-vendor-arbitrage-instrument`.

## ADDED Requirements

### Requirement: Model Catalog

The system SHALL maintain a durable catalog of routable models keyed by
`(vendor, model, endpoint_kind)` where `endpoint_kind ∈ {vendor-cli, vendor-sdk, openrouter, local}`,
carrying per-Mtok pricing, benchmark quality priors, observed latency, context limits, and
availability state. Catalog reads MUST be served from coordinator storage without calling any
external API on the read path.

#### Scenario: Catalog row served without external calls

- **WHEN** a routing decision requests candidates for an archetype
- **THEN** candidate rows SHALL be returned from coordinator storage
- **AND** no OpenRouter or vendor API call SHALL occur on the read path

### Requirement: OpenRouter Catalog Refresher

The system SHALL refresh catalog pricing, model availability, and benchmark/ranking priors from
the OpenRouter REST API on a configurable schedule using a standing API key, and SHALL record a
refresh timestamp per row. A failed refresh MUST NOT invalidate existing catalog data; rows older
than a configurable staleness threshold SHALL be flagged stale in provenance.

#### Scenario: Scheduled refresh updates pricing

- **WHEN** the refresher runs and OpenRouter reports a changed per-Mtok price for a model
- **THEN** the catalog row SHALL be updated with the new price and refresh timestamp

#### Scenario: Refresh failure degrades gracefully

- **WHEN** the OpenRouter API is unreachable during a scheduled refresh
- **THEN** existing catalog rows SHALL remain served
- **AND** subsequent routing decisions using stale rows SHALL note staleness in decision provenance

### Requirement: Local Endpoint Registration

The system SHALL support registering local OpenAI-compatible endpoints (e.g. Ollama, vLLM) as
catalog entries with `endpoint_kind=local` via `agents.yaml` `base_url` configuration, SHALL
health-probe them on the refresher schedule, and SHALL seed their quality priors from a gen-eval
calibration suite rather than public benchmarks.

#### Scenario: Unhealthy local endpoint excluded

- **WHEN** a local endpoint fails its health probe
- **THEN** its catalog row SHALL be marked unavailable
- **AND** the resolver SHALL exclude it from candidates until a probe succeeds

### Requirement: Adaptive Selection Resolver

The system SHALL expose a `select_model_for_task` operation that ranks feasible candidates by a
transparent linear utility — quality (benchmark prior blended with task-type posterior by
sample-size confidence) minus weighted normalized cost and latency — and returns the selected
candidate, ranked alternatives, and a decision-provenance record. Objective weights SHALL come
from named profiles (`quality-first`, `balanced`, `cost-first`, `resilience`) selectable per
archetype/phase and overridable per call.

#### Scenario: Posterior outweighs benchmark prior with sufficient samples

- **WHEN** a model's task-type posterior has sample size above the confidence threshold and
  contradicts its benchmark prior
- **THEN** the blended quality score SHALL weight the posterior above the prior for that task type

#### Scenario: Objective profile changes the winner

- **WHEN** the same task is resolved under `cost-first` instead of `quality-first`
- **THEN** the resolver MAY select a cheaper candidate
- **AND** both decisions SHALL record their profile and weights in provenance

### Requirement: Hard Feasibility Constraints as Mutable Policy

The system SHALL evaluate hard feasibility constraints — vendor role/modality eligibility
(including subscription EULA terms such as Claude-subscription programmatic-ineligibility), data
residency, and capability floors — as mutable Cedar policy over agent/vendor attributes BEFORE
scoring, and infeasible candidates MUST NOT be scored or selected.

#### Scenario: EULA-ineligible vendor never scored

- **WHEN** a programmatic work unit is routed while a vendor's policy marks it programmatic-ineligible
- **THEN** that vendor's candidates SHALL be excluded before ranking
- **AND** the exclusion and policy version SHALL appear in decision provenance

### Requirement: Exploration Budget

The system SHALL support deliberate exploration (selecting a lower-ranked candidate to gather
posterior data) governed by two configurable ceilings — an eligible-task percentage and a monthly
exploration spend cap — and SHALL mark exploration decisions in provenance. Premium-archetype
phases SHALL be exploration-ineligible unless explicitly configured otherwise. When either ceiling
is exhausted the resolver MUST select purely by exploitation ranking.

#### Scenario: Exhausted budget forces exploitation

- **WHEN** the monthly exploration spend cap is reached
- **THEN** subsequent decisions SHALL select the top-ranked candidate
- **AND** no decision SHALL be marked as exploration until the budget window resets

### Requirement: Monthly Metered Spend Ceiling

The system SHALL accrue actual metered dispatch cost (OpenRouter reconciled via generation
lookups; SDK dispatch via token counts × price table) into a spend ledger, and SHALL deny
metered-endpoint selection when the configured monthly ceiling would be exceeded, falling back to
subscription/local candidates.

#### Scenario: Ceiling exceeded falls back to non-metered

- **WHEN** cumulative metered spend for the month has reached the ceiling
- **THEN** the resolver SHALL exclude metered endpoints from candidates
- **AND** record the ceiling exclusion in decision provenance

### Requirement: Metered-Counterfactual Cost Ledger

The system SHALL record, for every routed unit of work, actual spend and the metered-API
counterfactual cost, exposing cumulative `(metered_baseline − actual_spend)` as the savings
metric. Estimated token counts MUST be labelled as estimates, and the metric SHALL be reportable
including and excluding estimated entries.

#### Scenario: Ledger entry on subscription dispatch

- **WHEN** a work unit completes on a subscription CLI vendor
- **THEN** a ledger entry SHALL record actual marginal cost and the metered counterfactual
- **AND** cumulative net savings SHALL be updated

### Requirement: Feedback Posterior Aggregation

The system SHALL aggregate task-outcome feedback into per-`(model, task_type, metric)` posteriors
from weighted sources (gen-eval scores, validation/review outcomes and vendor switches, procedural
memory counters, transcript struggle signals) using exponential decay, and SHALL store sample
sizes so the resolver can blend by confidence.

#### Scenario: Vendor switch updates posteriors

- **WHEN** a recorded vendor switch carries expected-vs-observed cost and latency deltas
- **THEN** the aggregation job SHALL fold the observation into the affected model's posterior
- **AND** increment its sample size

### Requirement: Signal Recording and Decision Provenance

The system SHALL record signal events (throttles, enforcement anomalies, canary results, ToS
diffs, routing decisions) to the append-only audit log with labelled telemetry, and SHALL persist
for every routing decision a provenance record containing inputs (priors, posteriors, constraints,
profile weights, budget state), the chosen candidate, alternatives, and the realised outcome
reference. Recording MUST NOT block the caller and MUST no-op cleanly when disabled.

#### Scenario: Every selection is reconstructible

- **WHEN** an operator queries a past routing decision
- **THEN** the provenance record SHALL contain sufficient inputs to explain the ranking
- **AND** link to the realised outcome once known

### Requirement: ToS Monitor Probe

The system SHALL periodically fetch and hash each vendor's automation-clause terms URL, emit a
compliance signal on change, and freeze dispatch to that vendor pending operator acknowledgment.

#### Scenario: ToS change freezes vendor

- **WHEN** the fetched terms hash differs from the last recorded hash
- **THEN** a compliance signal SHALL be emitted
- **AND** the vendor SHALL be excluded from routing until an operator acknowledges

### Requirement: Model Canary Probe

The system SHALL periodically send a fixed canary prompt per catalog model, fingerprint the
response, and on drift beyond threshold invalidate that model's priors and posteriors (marking
them low-confidence) and emit a quality-drift signal.

#### Scenario: Canary drift invalidates posteriors

- **WHEN** a model's canary fingerprint drifts beyond the configured threshold
- **THEN** its posteriors SHALL be marked low-confidence
- **AND** a quality-drift signal SHALL be recorded

### Requirement: Tripwires Flip System Posture

The system SHALL evaluate tripwire conditions — ToS diff (vendor freeze), enforcement pattern
(modality demotion), realized savings below maintenance threshold (economic kill
recommendation), canary drift (prior invalidation) — and each posture flip SHALL itself be
recorded as a signal with its triggering evidence.

#### Scenario: Economic kill recommendation

- **WHEN** cumulative net savings falls below the configured maintenance threshold
- **THEN** an economic-kill signal SHALL be emitted recommending disabling adaptive routing
- **AND** the recommendation SHALL include the ledger evidence

### Requirement: Static-Tier Fallback and Kill Switch

The system SHALL gate adaptive routing behind a single feature flag; when the flag is off, or the
resolver errors or exceeds its timeout, callers SHALL receive the existing static archetype-tier
resolution. Disabling the flag MUST restore pre-change behavior without data loss.

#### Scenario: Resolver timeout falls back

- **WHEN** the resolver does not respond within its configured timeout
- **THEN** the caller SHALL proceed with static tier resolution
- **AND** the fallback SHALL be recorded as a signal event
