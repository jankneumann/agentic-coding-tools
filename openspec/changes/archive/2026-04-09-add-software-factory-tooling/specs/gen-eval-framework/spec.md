# gen-eval-framework Specification Delta

## ADDED Requirements

### Requirement: Scenario Pack Manifest

The gen-eval framework SHALL support a machine-readable scenario-pack manifest that classifies scenarios by visibility, provenance, determinism, and ownership.

The manifest SHALL support at minimum:
- `visibility`: `public` or `holdout`
- `source`: `spec`, `contract`, `doc`, `incident`, `archive`, or `manual`
- `determinism`: `deterministic`, `bounded-nondeterministic`, or `exploratory`
- `owner`: responsible team or change-id
- `promotion_status`: `draft`, `candidate`, `approved`

#### Scenario: Manifest validates public vs holdout classification
Given a scenario-pack manifest containing both public and holdout entries
When the framework loads the manifest
Then each entry is validated against the allowed visibility enum

#### Scenario: Manifest preserves provenance metadata
Given a scenario-pack manifest entry derived from an incident
When the entry is loaded
Then the framework records `source=incident` and preserves the linked incident reference

#### Scenario: Invalid visibility is rejected
Given a manifest entry with `visibility=private`
When the manifest is validated
Then validation fails with a clear enum error

### Requirement: Visibility-Aware Scenario Execution

The framework SHALL support visibility-aware scenario filtering and reporting.

Implementation-visible workflows SHALL execute `public` scenarios only unless explicitly overridden for diagnostic use. Validation and cleanup gates SHALL support executing both `public` and `holdout` scenarios, with separate reporting for each visibility bucket.

#### Scenario: Implementation run excludes holdout scenarios
Given a manifest with public and holdout scenarios
When gen-eval runs in implementation context
Then only public scenarios are selected for execution

#### Scenario: Cleanup gate includes holdout scenarios
Given a validation context with holdout scenarios available
When cleanup validation runs
Then the holdout scenarios are executed and reported separately from public scenarios

#### Scenario: Report includes visibility coverage
Given a completed evaluation run
When the report is generated
Then it includes pass/fail counts and coverage percentages grouped by visibility

#### Scenario: Implementation context rejects explicit holdout request
Given an implementation-context run with an explicit request to include holdout scenarios
When gen-eval validates the request
Then it rejects the request with a clear error indicating holdout scenarios are not available in implementation context

### Requirement: DTU Scaffold From Public Docs

The framework SHALL support generating a DTU-lite scaffold from public SDK/API documentation, examples, auth guidance, and error-mode descriptions.

The scaffold SHALL produce:
- a descriptor seed
- fixture placeholders
- an unsupported-surface list
- a fidelity report

The fidelity report SHALL determine whether the resulting DTU is eligible for holdout-backed validation.

#### Scenario: DTU scaffold generated from public docs
Given public SDK/API docs and examples for an external system
When the DTU scaffold flow runs
Then it creates a descriptor seed, fixture structure, and unsupported-surface list

#### Scenario: Fidelity report marks low-confidence twin as non-holdout
Given a DTU scaffold with low conformance or large unsupported surface
When the fidelity report is generated
Then the report marks the DTU as not eligible for holdout promotion

#### Scenario: Fidelity report captures live probe results
Given a DTU scaffold that can be probed against a live system
When fidelity checks run
Then the report records the probe outcomes and resulting conformance score

### Requirement: Multi-Source Scenario Bootstrap

The framework SHALL support bootstrapping scenarios from OpenSpec spec deltas, contract artifacts, incidents, archived exemplars, and public docs in addition to hand-authored templates.

Bootstrapped scenarios SHALL preserve source metadata in the scenario-pack manifest so downstream users can distinguish normative scenarios from mined or inferred ones.

#### Scenario: Bootstrap from spec deltas
Given an OpenSpec change with requirement scenarios
When the bootstrap flow runs
Then it emits scenario seeds linked to the originating requirement refs

#### Scenario: Bootstrap from archived exemplar
Given a mined exemplar from an archived OpenSpec change
When scenario bootstrap runs
Then it emits a new draft scenario with `source=archive`

#### Scenario: Bootstrap from contract artifact
Given an OpenAPI or schema contract
When scenario bootstrap runs
Then it emits scenario seeds that reference the contract path in their metadata

#### Scenario: Bootstrap from empty spec delta produces no scenarios
Given a spec delta with no requirement scenarios defined
When the bootstrap flow runs
Then it produces zero scenario seeds and logs a warning indicating no source material

#### Scenario: Bootstrap from malformed source skips gracefully
Given a corrupt or unparseable archived artifact
When scenario bootstrap runs
Then the malformed source is skipped with a warning and remaining sources are processed normally
