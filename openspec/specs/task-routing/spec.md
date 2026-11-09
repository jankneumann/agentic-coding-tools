# task-routing Specification

## Purpose
TBD - created by archiving change declare-the-routing-cost-policy-the-router-obeys. Update Purpose after archive.
## Requirements
### Requirement: Cost-aware assignment selection

The router SHALL read a schema-validated cost policy with ordered local subscription, cloud subscription, and metered API tiers. It SHALL choose the first tier containing a feasible assignment for the requested archetype, then rank assignments within that tier using the existing utility scorer.

#### Scenario: Local subscription can serve the task

- **WHEN** a local subscription lane is available and eligible, alongside cloud subscription and metered lanes
- **THEN** the router SHALL select from the local subscription tier, regardless of a lower-tier candidate's utility score.

#### Scenario: Local subscription window is exhausted

- **WHEN** the local subscription lane is rate limited and a cloud subscription lane can serve the task
- **THEN** the router SHALL select the cloud subscription tier.

#### Scenario: Metered API is last resort

- **WHEN** no subscription tier can serve the requested model or both subscription tiers are exhausted
- **THEN** the router MAY select the metered tier.
- **AND** it SHALL NOT select that tier while an eligible subscription candidate remains.

### Requirement: Cost tier provenance

Each successful coordinator decision SHALL record the served cost tier in response provenance and in its durable routing decision record.

#### Scenario: Post-run spend audit

- **WHEN** a routing decision is read after dispatch
- **THEN** its provenance SHALL identify whether a subscription or metered tier served it.
