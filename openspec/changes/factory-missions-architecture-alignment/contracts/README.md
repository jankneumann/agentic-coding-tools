# Contracts — Factory Missions Architecture Alignment

This change introduces and modifies the following machine-readable interfaces. Each is the coordination boundary between work packages, so changes here MUST be reviewed before any implementation work begins.

## Inventory

| File | Type | Status | Owner WP | Consumers |
|---|---|---|---|---|
| `frontend-descriptor.schema.json` | JSON Schema | NEW | wp7 | wp7 (sample), `evaluation/gen_eval/descriptors/*-frontend.yaml` files |
| `agents-policy-schema.json` | JSON Schema fragment | NEW | wp6 | `agent-coordinator/agents.yaml` validation, dispatcher logic |
| `gen-eval-cli.md` | CLI flag specification | NEW | wp3 | wp4 (validate-feature handler), wp7 (Playwright skill) |
| `findings-vendor-source.md` | Naming convention | NEW | wp5 | gen-eval emitter (wp5), Playwright emitter (wp7), consensus synthesizer (wp5) |
| `../../../schemas/review-findings.schema.json` | JSON Schema (existing) | MODIFIED | wp5 | All vendor-source emitters |

## Sub-types Evaluated

OpenAPI contracts: **N/A** — no HTTP API endpoints introduced.
Database contracts: **N/A** — no schema changes.
Event contracts: **N/A** — no new events.
Type generation stubs: **N/A** — Pydantic and TypeScript stubs derived from `review-findings.schema.json` are produced by the existing build, not by this change.

## Modification: review-findings.schema.json

Adds `behavioral_failure` to the `type` enum at `openspec/schemas/review-findings.schema.json` (current location: line 18 per Step-2 exploration). This is the only modification to an existing schema. All other contract changes are additive (new files).
