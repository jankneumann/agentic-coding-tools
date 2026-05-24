# Contracts — add-kanban-viz-docker-e2e

**No new HTTP, SSE, or file-format contracts are authored in this change.**

This change is purely operational tooling around the existing coordinator surface:

- The orchestrator (`agent-coordinator/scripts/e2e_kanban.py`) consumes the public Docker Compose surface and the existing `/health`, `/issues/create`, `/issues/update`, `/issues/close`, `/events/auth`, `/events/work` HTTP endpoints. No new endpoint shapes.
- The seed script (`agent-coordinator/scripts/seed_kanban_board.py`) consumes the same endpoints plus `/issues/list`.
- The vitest transition test exercises the SSE `transition` event shape already pinned by `add-coordinator-kanban-viz`'s `contracts/schemas/events/transition.json` and the matching `TransitionPayload` interface in `apps/kanban-viz/src/lib/coordinator-types.ts`.

## Canonical Contracts Consumed (Read-Only References)

| Surface | Owner | Canonical Path |
|---|---|---|
| HTTP API | `add-coordinator-kanban-viz` (archived) | `openspec/changes/archive/2026-05-22-add-coordinator-kanban-viz/contracts/README.md` |
| SSE `transition` event | `add-coordinator-kanban-viz` (archived) | `openspec/changes/archive/2026-05-22-add-coordinator-kanban-viz/contracts/schemas/events/transition.json` |
| TypeScript types | `apps/kanban-viz/` | `apps/kanban-viz/src/lib/coordinator-types.ts` |
| Compose surface | `agent-coordinator/` | `agent-coordinator/docker-compose.yml` |

The schema requires this `contracts/` directory and `openapi.primary` / `openapi.files` entries even when no new contracts are authored; this README serves as the placeholder pointing back at the canonical sources rather than duplicating them.

If a future iteration of the orchestrator generalizes to other services (see design.md "Open Questions"), it WILL author new contracts (probably a `live-service-testing`-compliant launcher schema) at that time; this README would be replaced rather than amended.

## Why No Sub-schemas

The work-packages.yaml schema requires `contracts.openapi.files: minItems=1`, which forced this file to exist. The single entry in `openapi.files` is this README itself, serving as the operational-contract entrypoint for the change. Pointing at proposal.md or design.md would be semantically wrong (those describe rationale, not contract shape); pointing at the archived parent's contracts would create a cross-change file dependency that openspec doesn't currently track.
