# Report interventions per bug and rank gaps in improve-harness

> Parent roadmap: `evidence-grounded-debugging`
> Change ID: `report-interventions-per-bug-and-rank-gaps`
> Effort: M
> Priority: 4

## Summary

Make agent-metrics report human interventions per bug over time, in total and per gap category, and make improve-harness rank categories by frequency and emit proposal stubs for categories above a configured threshold.

## Dependencies

- `ri-10`

## Acceptance Outcomes

- agent-metrics outputs interventions-per-bug with a per-category breakdown for a fixture dataset.
- The report shows a time series so the trend in interventions per bug is observable across periods.
- improve-harness emits at least one candidate-work stub per category that exceeds a configured frequency threshold.

## Rationale

Interventions per bug is the proposal's honest gauge of autonomy and its success criterion. Ranking categories turns them into an infrastructure backlog.
