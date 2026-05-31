# Usage Dashboard

## ADDED Requirements

### Requirement: Usage Dashboard Application

There SHALL be a React + TypeScript + Vite application at `apps/usage-stats/`
that visualizes usage from the coordinator `/usage/*` API, reusing the
kanban-viz access pattern (`Authorization: Bearer`, SSE primary with polling
fallback).

#### Scenario: Dashboard renders daily/weekly/all-time rollups

- **WHEN** the dashboard loads with a reachable coordinator
- **THEN** it SHALL display token and estimated-cost charts for daily, weekly,
  and all-time windows

#### Scenario: Live refresh via SSE

- **WHEN** a `usage.recorded` event arrives on the SSE stream
- **THEN** the dashboard SHALL update the affected charts without a full reload

#### Scenario: Polling fallback when SSE fails

- **WHEN** the SSE connection cannot be established
- **THEN** the dashboard SHALL fall back to periodic polling and remain
  functional

### Requirement: Per-Vendor and Per-Model Filtering

The dashboard SHALL allow filtering by vendor and by model, and the active
filter state SHALL be reflected in the URL so a filtered view is bookmarkable.

#### Scenario: Vendor filter updates charts and URL

- **WHEN** the user selects a single vendor
- **THEN** the charts SHALL show only that vendor's usage and the URL SHALL
  encode the selected vendor

#### Scenario: Bookmarked filter restores on load

- **WHEN** the dashboard is opened with filter state present in the URL
- **THEN** it SHALL restore that vendor/model filter selection on load

### Requirement: Estimated-Cost Labelling

The dashboard SHALL label all monetary figures as estimates and SHALL render
models with no known price as "n/a" rather than zero cost.

#### Scenario: Unknown-price model shows n/a

- **WHEN** a model has no pricing entry
- **THEN** its cost column SHALL display "n/a" while its token counts remain
  visible
