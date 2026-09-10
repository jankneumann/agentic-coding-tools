# Candidate-work integration contracts

This change introduces no new schema. It consumes these canonical contracts:

- `openspec/schemas/candidate-work.schema.json` — producer sidecars and candidate
  input to prioritize-proposals/plan-roadmap.
- `openspec/schemas/roadmap.schema.json` — mapped roadmap items and workspaces.
- `openspec/schemas/work-packages.schema.json` — implementation package plan.

## Sidecar contract

| Producer | Rich artifact retained | Candidate-work sidecar |
|---|---|---|
| bug-scrub | `bug-scrub-report.{md,json}` | `candidate-work.json` beside the report |
| improve-harness | capability-gap report / legacy proposal markdown | explicit candidate output or report-adjacent `candidate-work.json` |
| explore-feature | `docs/feature-discovery/opportunities.json` | `docs/feature-discovery/candidate-work.json` |

All sidecars are JSON arrays, validate fully before atomic replacement, serialize
with sorted keys and a trailing newline, and populate `provenance.generator`.

## Approved intake contract

The plan-roadmap intake accepts one schema-valid stub plus non-empty measurable
acceptance outcomes. It returns either a validated one-item new-roadmap payload or a
refine-roadmap add request. It does not write an existing roadmap itself.
