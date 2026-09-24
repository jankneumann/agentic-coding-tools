Perform an independent, read-only implementation review of change
`mirror-autopilot-phase-state-into-the-work-queue` at exact HEAD
`743be9ae07b7e74a7ce7cfe7bb62caff39d258a0`, against base branch
`openspec/roadmap-roadmap-supervisor-orchestration`.

Read the proposal, design, specs, tasks, contracts, work-packages, and the full
production/test/doc diff. Review every changed production surface, not only tests.
Return only one JSON object conforming to
`openspec/schemas/review-findings.schema.json`, with
`review_type="implementation"`, `target` set to the change id, and your real
vendor name. Every finding needs axis, severity, matching description prefix,
coherent disposition, package_id, file_path, and precise line_range. Include
severity `none` positive observations when an axis is sound; do not return an
empty review for this non-empty diff.

Pay special attention to:

- migration 037 security, rollback/compatibility, claim exclusion, trigger
  behavior, PostgreSQL syntax, and live-PostgreSQL evidence;
- full-array label replacement being limited to exclusively owned projection
  issue rows, never ordinary issues;
- exact 409 reconciliation detection and all non-matching error semantics;
- runner `project-state` error/exit behavior, coordinator-free isolation, and
  every durable state writer;
- `enter_escalate` sequence advancement at every direct transition;
- SSE snapshot coalescing, boundedness, cleanup/unsubscribe behavior, event
  ordering, and leak/backpressure risks;
- OpenAPI revision/path/problem response parity with runtime behavior;
- canonical skill source and mirrored `.agents`/`.claude` copies.

Treat critical/high/medium correctness, security, compatibility, architecture,
or resilience defects as blocking `fix` findings. Do not modify files.
