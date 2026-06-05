# cross-vendor-arbitrage Specification

## Purpose

Provide a kill-switchable instrument that records signals about cross-vendor agent routing, maintains a metered-counterfactual cost ledger, detects shifts in the conditions that make cost arbitrage pay (ToS terms, quota economics, model quality), and drives a deliberately simple static-priority router behind a mutable hard/soft constraint split. The instrument is the durable deliverable; the arbitrage logic it serves is treated as a removable add-on.

## ADDED Requirements

### Requirement: Signal Recording Across Five Families

The system SHALL record arbitrage signal events across five families — compliance surface, cost/quota economics, quality/model drift, integration/composition cost, and decision provenance — to an append-only store, and SHALL emit corresponding labelled telemetry measurements. Signal recording MUST NOT block the caller and MUST no-op cleanly when the instrument is disabled or the coordinator/telemetry backend is unavailable.

#### Scenario: A cost/quota signal is recorded with vendor labels

- **WHEN** a unit of work completes on a given `(vendor, model, modality, archetype)`
- **THEN** an append-only signal event of family `cost_quota` SHALL be recorded with the token counts and the work-unit identifier
- **AND** an OpenTelemetry measurement SHALL be emitted on the `coordinator.signal` meter carrying `vendor`, `model`, `modality`, and `archetype` labels

#### Scenario: A throttle event captures the invisible cap

- **WHEN** a vendor returns a hard rate-limit (HTTP 429) response
- **THEN** a `compliance` signal SHALL be recorded that includes the cumulative subscription usage observed at the moment of the throttle
- **AND** the record SHALL be queryable to triangulate the vendor's cap over time

#### Scenario: Recording degrades gracefully when disabled

- **WHEN** the instrument feature flag is off
- **THEN** signal recording calls SHALL return without error and without writing any event
- **AND** no telemetry measurement SHALL be emitted

### Requirement: Metered-Counterfactual Cost Ledger

The system SHALL record, for every routed unit of work, both the actual spend and the metered-API counterfactual cost, and SHALL expose the cumulative `(metered_baseline − actual_spend)` as the headline arbitrage-value metric. Where exact token usage is unavailable, the ledger SHALL record a clearly-labelled estimate and MUST allow the headline metric to be reported both including and excluding estimated entries.

#### Scenario: A ledger entry records actual and counterfactual cost

- **WHEN** a unit of work is dispatched to a subsidised subscription vendor
- **THEN** a ledger entry SHALL record the actual marginal cost and the metered-counterfactual cost derived from the versioned per-vendor price table
- **AND** the cumulative net-savings metric SHALL be updated

#### Scenario: Missing token usage is recorded as a labelled estimate

- **WHEN** a vendor adapter does not report token usage for a completed unit of work
- **THEN** the ledger entry SHALL use a heuristic estimate and set `estimated: true`
- **AND** the headline net-savings metric SHALL be reportable with and without estimated entries

### Requirement: ToS Monitor Probe

The system SHALL periodically fetch and content-hash each configured vendor's automation-clause URL and SHALL emit a `compliance` signal when a change is detected. The probe MUST detect change only; it MUST NOT adjudicate legality.

#### Scenario: A changed ToS clause emits a compliance signal

- **WHEN** the scheduled ToS monitor fetches a vendor automation-clause URL whose content hash differs from the last recorded hash
- **THEN** a `compliance` signal SHALL be recorded capturing the vendor, the URL, and the old and new hashes
- **AND** the change SHALL be made available to the tripwire evaluation

### Requirement: Model Canary Probe

The system SHALL periodically issue a fixed canary prompt to each configured model, fingerprint the response, and emit a `quality_drift` signal when the fingerprint changes, so that silent model substitutions under a fixed model name are detected.

#### Scenario: A drifted model fingerprint emits a drift signal

- **WHEN** the scheduled model canary fingerprints a model whose fingerprint differs from the last recorded value
- **THEN** a `quality_drift` signal SHALL be recorded for that `(vendor, model)`
- **AND** the drift SHALL be made available to the tripwire evaluation

### Requirement: Hard Feasibility Constraints as Mutable Policy

The system SHALL express vendor role and execution-modality eligibility as runtime-mutable policy rather than hardcoded logic, and the router SHALL reject any assignment that violates an eligibility constraint. Changing an eligibility value SHALL take effect without a code change or redeploy.

#### Scenario: A programmatic-ineligible vendor is rejected as a worker

- **WHEN** the router evaluates assigning a unit of work to a vendor whose eligibility marks it programmatic-ineligible under its current subscription
- **THEN** the policy check SHALL return not-allowed for that assignment
- **AND** the assignment SHALL be excluded from the feasible set

#### Scenario: An eligibility change takes effect without redeploy

- **WHEN** an operator updates a vendor's modality eligibility in the eligibility configuration
- **THEN** subsequent router feasibility checks SHALL honour the new value without a code change or process restart

### Requirement: Static-Priority Router

The system SHALL select an assignment from the feasible set using a static-priority policy — cheapest eligible tier first, spilling to the next vendor on a hard rate-limit, and preferring to keep a single work-package on one vendor unless a configured switching threshold is exceeded — and SHALL record the decision provenance for every selection. The router MUST expose a stable selection interface so a future optimiser can replace the policy without changing the signal layer.

#### Scenario: Router prefers the cheapest eligible tier

- **WHEN** the router selects among a feasible set containing multiple eligible vendors
- **THEN** it SHALL choose the cheapest eligible tier
- **AND** it SHALL record a `decision_provenance` signal capturing the inputs, the chosen assignment, and the constraints applied

#### Scenario: Router spills on rate-limit

- **WHEN** the currently selected vendor returns a hard rate-limit
- **THEN** the router SHALL select the next-cheapest eligible vendor from the feasible set
- **AND** SHALL record the spill in the decision provenance

### Requirement: Tripwires Flip System Posture

The system SHALL evaluate declarative tripwire thresholds against the signal substrate, and each tripwire that fires SHALL both record a learning entry describing the world-change and set a posture flag that subsequent routing honours.

#### Scenario: A ToS-diff tripwire freezes dispatch

- **WHEN** a `compliance` signal indicates an automation-clause change for a vendor
- **THEN** the ToS-diff tripwire SHALL set a freeze posture flag for that vendor
- **AND** subsequent router feasibility checks SHALL exclude that vendor until the freeze is cleared
- **AND** a learning entry SHALL be recorded describing the freeze and its cause

#### Scenario: An economic-kill tripwire fires when arbitrage stops paying

- **WHEN** the cumulative net-savings metric falls below the configured maintenance-cost threshold over the trailing window
- **THEN** the economic-kill tripwire SHALL record a learning entry recommending fallback to single-vendor operation

### Requirement: Landscape Digest

The system SHALL generate, on demand and on a schedule, a vendor-landscape digest assembled from the signal substrate, reporting at minimum: per-vendor utilisation against inferred cap, cumulative net savings versus the metered baseline, detected ToS changes, detected model drift, and the integration-cost verdict.

#### Scenario: The digest reports the headline arbitrage metric

- **WHEN** the digest is generated
- **THEN** it SHALL include the cumulative net-savings metric reported both including and excluding estimated ledger entries
- **AND** it SHALL list any tripwires that fired during the reporting window

### Requirement: Single Kill Switch

The instrument SHALL be controllable by a single feature flag defaulting to off. When the flag is off, the router SHALL fall back to the pre-existing default dispatch behaviour, the probes SHALL NOT schedule, and signal recording SHALL no-op.

#### Scenario: Disabling the instrument restores default dispatch

- **WHEN** the instrument feature flag is off
- **THEN** work dispatch SHALL behave identically to the system without the instrument installed
- **AND** no probe SHALL be scheduled and no signal SHALL be recorded
