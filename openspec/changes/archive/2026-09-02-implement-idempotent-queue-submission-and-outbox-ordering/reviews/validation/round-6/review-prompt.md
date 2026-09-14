# Canonical Validation 7 / round-six independent review

Read-only review of the branch `openspec/implement-idempotent-queue-submission-and-outbox-ordering` at evidence head `937a18291a6a68670aa70f32d1173ffd7d1c1fe5`, whose product tree is unchanged since exact product HEAD `377b9deb80d2c5f7869b5151d63d63b0d71824d0` / tree `d403701f6c32a7fbb406391d8d5e200a7df32ca2` (`b9884a0a` and `937a1829` add evidence and orchestration artifacts only). Do not modify files and do not read `loop-state.json`.

This round must critique **both** the validation evidence **and the new product code** landed since the round-five convergence at `be1bada1`. Four product commits postdate that review:

- `dda2834f` — dropped `_agent_identity()` injection from `proxy_submit_work` / `proxy_reconcile_work_projection` (the `extra="forbid"` 422), and added the trust/guardrail screen to `WorkQueueService.reconcile_projection()`;
- `e973d77a` — migration `036_terminal_completion_guard.sql` restricting `complete_task`'s UPDATE to `status IN ('claimed','running')` with `reason='task_not_active'`, plus the reconcile audit-log call;
- `760e1415` — autopilot escalation persistence projection and projection-envelope classification (`skills/autopilot/scripts/autopilot.py`);
- `bd0c0fdc` — asyncpg `jsonb`/`json` codec registration on `DirectPostgresClient` (`agent-coordinator/src/db_postgres.py`).

Independently critique correctness, security, resilience, compatibility, and evidence integrity. Inspect:

- `openspec/changes/implement-idempotent-queue-submission-and-outbox-ordering/validation-report.md`, especially the `Canonical Validation 7` section, plus `architecture-impact.md` and `handoffs/validation-7-1.json`;
- the four product commits above and their tests, in the working tree at HEAD — not only the report's description of them;
- whether `bd0c0fdc`'s codec can double-encode or mis-decode values (in particular a parameter that is already a serialized JSON string, and `NULL` / non-dict payloads), and whether the encoder/decoder pair round-trips for every `jsonb`/`json` column the queue and projection code reads or writes;
- whether migration `036`'s status guard can refuse a legitimate `complete_task` for a row that is genuinely `claimed` or `running` (including the claimed→running transition and retry paths), and whether the new `task_not_active` result shape is handled by every caller;
- whether `dda2834f`'s identity removal loses any authorization signal the routes relied on, and whether the reconcile guardrail screen matches `submit()`'s semantics on the same scan text;
- retained ZAP evidence hashes/gate under `validation-evidence/security/`, the fresh PostgreSQL/raw-bootstrap ledger claims (39/39, `ensure_schema()` `[]`), teardown claims, and the exact-head GitHub CI claims for PR #457 at `377b9deb`;
- whether the reused live evidence actually covers the final product tree, and whether any post-evidence product or dependency change invalidates it;
- whether the `Package Evidence` warning and advisory `Architecture` DEGRADED statuses remain honestly scoped and non-blocking.

Verify claims against the repository rather than restating the report.

Return only JSON conforming to `openspec/schemas/review-findings.schema.json` with `review_type: "implementation"`, `target: "validation-evidence"`, and `package_id: "validation-evidence"`. Use your real vendor name in `reviewer_vendor`. Every finding must include `axis`, `severity`, matching description prefix, coherent disposition, concrete `file_path`, and `line_range`. Any correctness/security/resilience/compatibility/evidence-integrity defect that invalidates the Validation 7 PASS is `severity: "critical"` and `disposition: "fix"`. If no blocker exists, include positive `severity: "none"` findings across at least two axes with `disposition: "accept"` rather than an empty findings array.
