# observability Specification (delta)

## ADDED Requirements

### Requirement: Usage and Routing Dashboard

The system SHALL provide a web dashboard (patterned on the kanban-viz stack: React + TypeScript +
Vite, Bearer-authenticated coordinator API access with SSE or polling) rendering per-vendor/model
token and spend totals, cumulative counterfactual savings, the model×task-type posterior
scoreboard, and exploration budget burn-down. Entries derived from estimated token counts SHALL be
visually labelled as estimates.

#### Scenario: Scoreboard reflects posteriors

- **WHEN** the dashboard loads the scoreboard view
- **THEN** per-(model, task-type) quality posteriors with sample sizes SHALL be rendered from the
  coordinator API

#### Scenario: Estimates are distinguishable

- **WHEN** a spend total includes estimated entries
- **THEN** the dashboard SHALL label the estimated portion distinctly

### Requirement: Routing Telemetry

Routing decisions, fallbacks, exploration selections, and tripwire events SHALL be emitted as
labelled OpenTelemetry measurements on the `coordinator.signal` meter with
`vendor`/`model`/`endpoint_kind`/`archetype` labels.

#### Scenario: Fallback visible in telemetry

- **WHEN** a resolver timeout causes static-tier fallback
- **THEN** a measurement with a `fallback` label SHALL be emitted
