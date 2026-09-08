# Independent plan review: mirror-autopilot-phase-state-into-the-work-queue

Review the OpenSpec plan for `mirror-autopilot-phase-state-into-the-work-queue` as a read-only, independent reviewer. Read every artifact under:

- `openspec/changes/mirror-autopilot-phase-state-into-the-work-queue/`

Then inspect the actual implementation boundaries the plan relies on, including at least:

- `skills/autopilot/SKILL.md`
- `skills/autopilot/scripts/autopilot.py`
- `skills/autopilot/scripts/runner.py`
- `skills/coordination-bridge/scripts/coordination_bridge.py`
- the coordinator issue/work-queue services and `/issues/list` route
- `apps/kanban-viz/src/hooks/useCoordinator.ts`

Evaluate all eight review axes and work-package validity. Pay special attention to these possible failure seams:

1. The real Autopilot host is prose plus `runner.py`; the plan must name every canonical state-write path that needs post-write projection.
2. Coordinated projection must be explicitly selected and injected; local-parallel and sequential tiers must perform zero coordination-bridge imports, availability probes, or requests.
3. Projection must happen only after all durable state writes, and a save failure must suppress projection.
4. Resume reconciliation must run after loading durable state but before pending-gate handling or any phase work.
5. The canonical work-queue row must be labelled `change:<change_id>` and actually visible through the existing `POST /issues/list` query contract used by kanban.
6. Canonical-row label-update partial failures must be degraded, retryable, and idempotent without creating duplicate rows.
7. Queue responses and queue state must remain strictly non-authoritative for `LoopState`.
8. Tests must prove coordinator-free tiers have zero imports/probes, not merely zero successful requests.

Return ONLY one JSON object conforming exactly to `openspec/schemas/review-findings.schema.json`; do not use markdown fences or surrounding prose. Set:

- `review_type` to `plan`
- `target` to `mirror-autopilot-phase-state-into-the-work-queue`
- `reviewer_vendor` to your CLI vendor name

Every finding must include `id`, `axis`, `severity`, `type`, `criticality`, `description`, `resolution`, and `disposition`. Match severity prefixes exactly (`Critical:`, `Nit:`, `Optional:`, `FYI:`; severity `none` needs no prefix). Critical/nit findings use `fix`; optional/fyi/none use `accept`, unless a genuine human decision requires `escalate`. Cite only paths and details you verified.
