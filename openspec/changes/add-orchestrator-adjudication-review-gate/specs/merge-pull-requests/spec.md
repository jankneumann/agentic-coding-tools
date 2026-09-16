## ADDED Requirements

### Requirement: Merge-time adjudication of unconfirmed high-impact findings

When merge-time vendor review is eligible and produces a consensus verdict, execution SHALL apply the shared adjudication predicate to the consensus findings. `blocking_count` alone SHALL NOT decide the merge, because a finding that no second vendor confirmed never contributes to it whatever its criticality. Each selected finding SHALL be adjudicated and the merge outcome SHALL be computed from the resulting verdicts.

#### Scenario: A single-vendor high finding is not silently advisory

- **WHEN** an eligible review returns `blocking_count: 0` alongside an unconfirmed high-impact judgment finding
- **THEN** execution SHALL NOT merge on the strength of `blocking_count` alone
- **AND** the finding SHALL be adjudicated before any merge decision.

#### Scenario: A verified blocking claim stops the merge

- **WHEN** adjudication verifies a selected finding whose impact is `blocking`
- **THEN** the node outcome SHALL be `pending` with a reason naming the verified finding
- **AND** the result SHALL carry the verdicts as merge evidence
- **AND** the merge SHALL NOT proceed.

#### Scenario: Refuted and non-blocking claims do not stop the merge

- **WHEN** every selected finding is refuted, or verified with `non_blocking` impact
- **THEN** adjudication SHALL NOT block the merge
- **AND** the verdicts SHALL still be recorded in the plan.

#### Scenario: An unverifiable blocking claim is a human gate

- **WHEN** adjudication returns an `unverifiable` claim whose impact is `blocking`
- **THEN** execution SHALL stop at a fail-closed human gate
- **AND** the gate SHALL be releasable only by explicit operator approval, never automatically.

#### Scenario: A report without evidence classes cannot be adjudicated

- **WHEN** an eligible review's consensus findings carry no `evidence_class`
- **THEN** execution SHALL stop with a reason distinguishing "not adjudicable" from "no blocking findings"
- **AND** it SHALL NOT merge on the strength of that report.
