# model-routing — Delta

## ADDED Requirements

### Requirement: Model Routing Data Plane

The coordinator database SHALL provide `model_catalog` and `model_posteriors` tables
keyed to distinguish thinking levels, with mandatory provenance on every prior and
posterior row.

#### Scenario: migration applies

- WHEN migration `035_model_routing.sql` is applied to a coordinator database
- THEN `model_catalog` SHALL exist with columns including vendor, model, thinking,
  endpoint_kind, benchmark_prior, and prior_source (NOT NULL when benchmark_prior is
  set), and `model_posteriors` SHALL exist keyed on (catalog_id, task_type, metric)
  with source and sample_size columns

#### Scenario: thinking-distinct candidates

- WHEN two catalog entries share vendor and model but differ in thinking level
- THEN they SHALL be distinct rows addressable as separate routing candidates

### Requirement: Benchmark Prior Import With Provenance

The system SHALL import completed benchmark trial results into the routing data
plane, aggregating rewards and costs per (vendor, model, thinking, task_type) and
stamping every written row with source `harbor-replay`.

#### Scenario: import from a sweep job

- WHEN the importer runs over a completed sweep job's trial records
- THEN it SHALL upsert `model_catalog.benchmark_prior` and `model_posteriors` rows
  for each observed (vendor, model, thinking, task_type) with quality,
  cost_per_task_usd (metered vendors), success_rate, latency, and sample_size

#### Scenario: provenance is mandatory

- WHEN the importer writes any prior or posterior row
- THEN the row SHALL carry source `harbor-replay`, and rows from judge-graded trials
  SHALL be distinguishable from deterministically verified ones

#### Scenario: idempotent re-import

- WHEN the importer is re-run over the same job
- THEN it SHALL NOT double-count trials (sample sizes and aggregates are unchanged)

### Requirement: Combo-Keyed Feedback Normalization

Feedback normalizers in `model_routing.feedback` SHALL key observations on the
composite (vendor, model, thinking) identity rather than vendor alone.

#### Scenario: thinking tiers stay separate

- WHEN observations exist for the same vendor and model at two thinking levels
- THEN `aggregate()` SHALL produce separate posterior groups for each thinking level

#### Scenario: vendor-note normalization

- WHEN `normalize_vendor_notes()` or `normalize_vendor_switch()` processes a roadmap
  record that names a vendor
- THEN the emitted model_id SHALL resolve to the catalog's composite identity, not
  the bare vendor string

### Requirement: Flagged Adaptive Phase Resolution

`resolve_for_phase` SHALL support an adaptive mode, disabled by default, that ranks
catalog candidates using the model_routing resolver with imported priors; with the
flag off, resolution behavior SHALL be unchanged from the static archetype mapping.

#### Scenario: flag off is inert

- WHEN `ROUTING_ADAPTIVE` is unset or disabled
- THEN `resolve_for_phase` SHALL return results identical to the current static
  resolution for all phases (verified by a golden test over all 15 phases)

#### Scenario: flag on ranks by priors

- WHEN `ROUTING_ADAPTIVE` is enabled and catalog rows with priors exist for the
  phase's archetype tier-set
- THEN the response's provider, model, and thinking SHALL come from
  `score_and_rank()` under the balanced objective profile, and `reasons[]` SHALL
  record that adaptive routing produced the selection

#### Scenario: constraints filter in both modes

- WHEN a candidate violates write-capability or provider trust constraints
- THEN it SHALL be excluded from selection in adaptive mode exactly as in static
  mode

#### Scenario: empty catalog falls back

- WHEN `ROUTING_ADAPTIVE` is enabled but no catalog candidates exist for the request
- THEN resolution SHALL fall back to the static mapping and record the fallback in
  `reasons[]`
