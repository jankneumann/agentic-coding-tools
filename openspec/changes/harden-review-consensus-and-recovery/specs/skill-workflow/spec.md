## ADDED Requirements

### Requirement: Fail-Closed Consensus Blocking Policy

Consensus synthesis SHALL preserve source dispositions and SHALL derive blocking state independently from cross-vendor match status.

#### Scenario: Unmatched actionable finding remains effective blocker
- **WHEN** a vendor reports an unmatched medium-or-higher finding with disposition `fix`, `regenerate`, or `escalate`
- **THEN** the consensus item SHALL retain that source disposition
- **AND** `summary.convergence_blocking_count` and compatibility `summary.blocking_count` SHALL include the finding until it is adjudicated

#### Scenario: Matching failure cannot produce a false zero
- **WHEN** multiple vendors describe actionable defects with wording or taxonomy that does not meet the match threshold
- **THEN** each unmatched actionable finding SHALL remain represented as provisional
- **AND** `summary.blocking_count` SHALL NOT be zero while any represented medium-or-higher actionable finding is unadjudicated

#### Scenario: Integration policy remains explicit
- **WHEN** a report contains only unconfirmed actionable findings
- **THEN** `summary.integration_blocking_count` SHALL follow the integration gate's warning-only policy
- **AND** `summary.convergence_blocking_count` SHALL follow the fail-closed autopilot policy

### Requirement: Evidence-Backed Finding Adjudication

Each consensus finding SHALL record source dispositions and an adjudication state of `unreviewed`, `fixed`, `false_positive`, `accepted_risk`, or `deferred` with rationale and evidence where applicable.

#### Scenario: Source refutation records false positive
- **WHEN** source reachability and byte-identity evidence refute a review recommendation
- **THEN** the finding SHALL be adjudicated `false_positive` with the evidence references and rationale
- **AND** the original vendor disposition SHALL remain in provenance while the finding no longer blocks

#### Scenario: Unsupported dismissal remains blocking
- **WHEN** an actionable finding is marked `false_positive` or `accepted_risk` without required rationale/evidence or authorization
- **THEN** adjudication validation SHALL fail
- **AND** the finding SHALL remain effective-blocking

#### Scenario: Deferred finding remains visible
- **WHEN** an actionable finding is adjudicated `deferred`
- **THEN** the report SHALL retain its tracking reference and source dispositions
- **AND** convergence SHALL remain blocked unless an explicit policy grants a waiver

### Requirement: Deterministic Match Provenance

Cross-vendor grouping SHALL use deterministic structured evidence before description similarity, SHALL tolerate configured taxonomy aliases, and SHALL record match method plus evidence.

#### Scenario: Paraphrased same-location defect is grouped
- **WHEN** two vendors report the same affected location with different wording or compatible type families
- **THEN** the matcher SHALL group them when structured evidence reaches the configured threshold
- **AND** the report SHALL record the match method, evidence, and score

#### Scenario: Input order does not change grouping
- **WHEN** the same vendor findings are synthesized in different vendor or finding orders
- **THEN** consensus groups, statuses, and summary counts SHALL be identical
- **AND** stable group identifiers SHALL not depend on the primary input order

#### Scenario: Ambiguous description stays separate
- **WHEN** two findings share generic wording but lack compatible structured evidence
- **THEN** the matcher SHALL keep them separate
- **AND** both findings SHALL retain their independent blocker state

### Requirement: Invalid Review Output Recovery

CLI, SDK, and async review dispatch SHALL classify malformed, empty, or schema-invalid completion output as `invalid_output` and SHALL execute a bounded recovery chain before final failure.

#### Scenario: Corrective redispatch succeeds
- **WHEN** a review attempt exits successfully but returns malformed findings output
- **THEN** the dispatcher SHALL retain a redacted diagnostic and perform at most one corrective redispatch to the same vendor/model
- **AND** a valid corrective response SHALL become the single quorum-eligible result with both attempts recorded

#### Scenario: Model fallback succeeds after invalid output
- **WHEN** the initial attempt and corrective redispatch both return invalid output
- **THEN** the dispatcher SHALL try configured fallback models in order within the logical request budget
- **AND** the successful fallback model plus fallback reason SHALL be recorded

#### Scenario: Invalid output chain is exhausted
- **WHEN** corrective redispatch and all configured model fallbacks fail validation
- **THEN** the vendor SHALL end with `success=false` and `error_class=invalid_output`
- **AND** the orchestrator MAY dispatch a replacement vendor but SHALL NOT count any failed attempt toward quorum

### Requirement: Review Attempt Diagnostics

Every logical vendor review SHALL persist bounded attempt provenance without embedding unredacted or unbounded process output in manifests.

#### Scenario: Manifest records attempt provenance
- **WHEN** a review request uses corrective or model fallback attempts
- **THEN** its manifest entry SHALL record requested archetype/tier, resolved provider model, thinking, parser stage, elapsed time, error class, attempt reason, and fallback reason for each attempt
- **AND** the final logical result SHALL identify exactly one terminal outcome

#### Scenario: Diagnostic text contains a secret-like value
- **WHEN** stdout or stderr contains credential-like or otherwise sensitive text
- **THEN** the manifest excerpt SHALL be redacted and truncated by the shared diagnostic helper
- **AND** logs, memory, and handoffs SHALL receive only the sanitized form

### Requirement: Shared Quorum Eligibility

The dispatcher, checkpoint writer, synthesizer, and convergence loop SHALL use one quorum-eligibility predicate that requires attributable, parsed, schema-valid completion output.

#### Scenario: Valid zero-finding review counts toward quorum
- **WHEN** a vendor returns a schema-valid findings document with an empty findings array
- **THEN** the logical result SHALL count once toward quorum
- **AND** `quorum_received` SHALL not depend on a non-empty finding count

#### Scenario: Exit-zero malformed output does not count
- **WHEN** a process exits zero but all recovery attempts fail output validation
- **THEN** its logical result SHALL not count toward quorum
- **AND** convergence SHALL fail closed with `quorum_lost` when the minimum eligible reviewer count is not met

## MODIFIED Requirements

### Requirement: Finding Trend Tracking and Stall Detection

The convergence loop SHALL track effective blocking finding counts per round and escalate if findings are not decreasing over a 3-round sliding window (that is, count at round N >= count at round N-2). Unadjudicated medium-or-higher findings with source disposition `fix`, `regenerate`, or `escalate` SHALL block in every round, including the final round. Findings with `disagreement` status SHALL always trigger escalation.

#### Scenario: Decreasing trend continues
- **WHEN** round 1 has 10 effective blockers, round 2 has 5, and round 3 has 6
- **THEN** trend analysis SHALL not classify the sequence as stalled because round 3 is below round 1
- **AND** remaining round-3 blockers SHALL still prevent convergence

#### Scenario: Flat trend triggers stall
- **WHEN** round 1 has 5 effective blockers, round 2 has 5, and round 3 has 5
- **THEN** the system SHALL escalate because round 3 is not below round 1
- **AND** the escalation SHALL retain the effective blocker details

#### Scenario: Unconfirmed actionable finding in final round
- **WHEN** the final round contains a single-vendor medium-or-higher actionable finding without a non-blocking adjudication
- **THEN** the finding SHALL block convergence
- **AND** exhausted iterations SHALL produce an inconclusive/escalated outcome rather than convergence

#### Scenario: Vendor disagreement
- **WHEN** vendors recommend conflicting dispositions for the same grouped finding
- **THEN** consensus SHALL classify the finding as `disagreement`
- **AND** the system SHALL transition to escalation regardless of round number
