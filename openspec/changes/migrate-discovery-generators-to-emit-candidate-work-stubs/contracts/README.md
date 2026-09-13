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
with sorted keys and a trailing newline, populate `provenance.generator`, normalize
change IDs to add/update/remove/refactor prefixes, and use the shared five-band
priority scale. Only blockers that resolve to exact change IDs enter `depends_on`;
free-form blockers remain inert rationale or tags.

Explicit source IDs are normalized as-is. Derived IDs always append the first eight
lowercase hex characters of SHA-256 over canonical provenance JSON, so membership in a
later batch cannot rename an earlier candidate. Duplicate final IDs fail the complete
write. Bug-scrub derives the base from the finding title, improve-harness from the
capability gap, and explore-feature from its stable ID or title when no explicit hint
exists. Explore-feature maps its weighted score through fixed D4 bands; shortlist rank
is provenance only. Improve-harness derives effort from affected-skill count, never
severity.

## Approved intake contract

The plan-roadmap intake accepts one schema-valid stub plus non-empty measurable
acceptance outcomes. New-roadmap mode also requires an approved roadmap ID and
capability and returns a complete schema-version-1 envelope using candidate provenance
as `source_proposal`. Existing-roadmap mode returns a refine add request without an
explicit execution priority, allowing refine-roadmap to assign max+1 while retaining
the candidate priority in the request rationale. Every dependency must map to exactly
one target-roadmap item and remains that item ID; archives are collision evidence, not
a reason to drop a dependency. Intake does not write an existing roadmap itself.
