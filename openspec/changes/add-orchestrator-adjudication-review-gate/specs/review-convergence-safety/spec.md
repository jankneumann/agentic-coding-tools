## ADDED Requirements

### Requirement: One shared adjudication predicate

Exactly one predicate SHALL decide whether a review finding requires adjudication, and every review gate SHALL use it. The predicate selects an open finding whose evidence class is `judgment`, whose consensus status is `unconfirmed`, and whose criticality is `high` or `critical`.

#### Scenario: Both gates select the same findings

- **WHEN** the convergence loop and the merge gate are given the same consensus findings
- **THEN** both SHALL select the same set of findings for adjudication
- **AND** neither SHALL pass a selected finding as advisory.

#### Scenario: The predicate has one definition

- **WHEN** the repository's Python sources are inspected
- **THEN** the finding-level predicate SHALL have exactly one definition under `skills/`
- **AND** the ledger-shaped and consensus-shaped entry points SHALL both delegate to it.

### Requirement: Persisted consensus findings carry their evidence class

A serialized consensus report SHALL record each finding's `evidence_class`, and the consensus-report schema SHALL declare it. A consumer SHALL NOT infer a missing evidence class.

#### Scenario: Evidence class survives serialization

- **WHEN** a consensus report containing a judgment finding is serialized
- **THEN** that finding's `evidence_class` SHALL be present in the serialized output
- **AND** the report SHALL validate against the consensus-report schema.

#### Scenario: A report without evidence classes is not adjudicable

- **WHEN** a gate reads a persisted report whose findings carry no `evidence_class`
- **THEN** the gate SHALL report the review as not adjudicable with a distinct reason
- **AND** it SHALL NOT treat the findings as either judgment or deterministic by default.

### Requirement: Orchestrator adjudication produces schema-valid verdicts

Each finding selected by the adjudication predicate SHALL receive exactly one schema-validated verdict. A verdict SHALL record whether the claim is `verified`, `refuted`, or `unverifiable`; `file:line` evidence, required when the claim is `verified` or `refuted`; `impact_if_true` as `blocking` or `non_blocking`; a recalibrated criticality; a justification; the adjudicator's identity; and the head SHA that was reviewed.

#### Scenario: Verdicts correspond one-to-one with the candidates

- **WHEN** a returned verdict set does not name every dispatched candidate exactly once, whether by duplicating a `finding_id`, naming a finding that was not dispatched, or omitting one that was
- **THEN** the verdict set SHALL be rejected as a whole
- **AND** the gate SHALL fail closed rather than acting on the verdicts that are well-formed.

#### Scenario: A verified or refuted claim carries evidence

- **WHEN** an adjudicator returns a verdict whose claim is `verified` or `refuted` without `file:line` evidence
- **THEN** the verdict SHALL be rejected as schema-invalid
- **AND** the finding SHALL remain unadjudicated.

#### Scenario: A verdict is bound to the head it reviewed

- **WHEN** a stored verdict's head SHA is not the current head
- **THEN** the verdict SHALL be treated as stale and SHALL NOT be reused
- **AND** the finding SHALL be adjudicated again.

#### Scenario: Same-family adjudication is flagged

- **WHEN** the adjudicator's vendor family is the family that authored the change under review
- **THEN** the gate result SHALL record that fact
- **AND** the verdict SHALL still be used.

### Requirement: Gate outcomes are computed from verdicts

A gate outcome SHALL be computed in code from the verdicts, and SHALL NOT be taken from an adjudicator's output. A `verified` claim whose impact is `blocking` blocks with a fix hand-off; an `unverifiable` claim whose impact is `blocking` routes to the human escalation queue; a `refuted` claim, or any claim whose impact is `non_blocking`, passes.

#### Scenario: Only unverifiable blocking claims reach a human

- **WHEN** the verdicts for a review contain no `unverifiable` blocking claim
- **THEN** no escalation SHALL be raised for that review.

#### Scenario: An adjudicator cannot declare the outcome

- **WHEN** an adjudicator's output names a gate outcome
- **THEN** that output SHALL have no effect on the computed outcome.

## MODIFIED Requirements

### Requirement: High-impact judgment requires adjudication

The convergence loop MUST stop without convergence when an open judgment-class finding is unconfirmed and has high or critical impact, and MUST adjudicate that finding before any automated fix or escalation. An unadjudicated finding SHALL NOT reach the automated fix callback; a finding whose verdict is `verified` with `blocking` impact SHALL. Escalation is the residual path for a claim the orchestrator can neither verify nor refute, not the first response.

#### Scenario: Unconfirmed high judgment

- **WHEN** consensus yields an unconfirmed high-impact judgment finding
- **THEN** convergence returns `adjudication_required`
- **AND** the finding is adjudicated before any escalation
- **AND** the automated fix callback is not invoked for it while it has no verdict

#### Scenario: Escalation carries only unverifiable blocking claims

- **WHEN** adjudication returns a mix of verified, refuted, and unverifiable verdicts
- **THEN** the escalation callback receives only the `unverifiable` claims whose impact is `blocking`
- **AND** a verified blocking claim blocks with a fix hand-off instead of escalating

#### Scenario: Medium judgment remains advisory

- **WHEN** consensus yields only unconfirmed medium-impact judgment findings
- **THEN** the existing advisory convergence behavior is preserved
