# Contracts Stub

This planning change introduces **artifact contracts** (roadmap state files) but no external API, DB schema, or event payload contracts yet.

## Artifact Contracts (in scope for implementation)

- `roadmap.yaml` — roadmap items, dependencies, status, and priority metadata
- `checkpoint.json` — resumable phase pointer and execution metadata
- `learning-log.md` — append-only learning entries consumed by future phases

## Evaluated External Contract Categories

- OpenAPI: Not applicable in this planning iteration
- Database: Not applicable in this planning iteration
- Events: Not applicable in this planning iteration

If implementation introduces coordinator APIs or persistent DB state for roadmap orchestration, this directory MUST be expanded with machine-readable contracts.
