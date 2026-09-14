Review the OpenSpec plan for change `route-parked-escalations-through-the-escalate-resume-gate` as an independent senior architect and code reviewer.

Read these artifacts in this repository worktree:

- `openspec/changes/route-parked-escalations-through-the-escalate-resume-gate/proposal.md`
- `openspec/changes/route-parked-escalations-through-the-escalate-resume-gate/design.md`
- `openspec/changes/route-parked-escalations-through-the-escalate-resume-gate/tasks.md`
- `openspec/changes/route-parked-escalations-through-the-escalate-resume-gate/specs/**/spec.md`
- `openspec/changes/route-parked-escalations-through-the-escalate-resume-gate/contracts/**`
- `openspec/changes/route-parked-escalations-through-the-escalate-resume-gate/work-packages.yaml`

Inspect the existing supervise execution adapter, gate router, approval-service integration, supervisor mirror/handoff projection, and related tests where needed to test feasibility and compatibility. Evaluate correctness, architecture, security, performance, observability, resilience, compatibility, contract consistency, retry safety, and executable verification coverage.

Pay particular attention to:

- strict separation between the already-acknowledged `apply` operation and retryable `route_parked_escalations`, so routing failure cannot replay `dispatch_fn` effects;
- proof that routing occurs only after durable parking and lease release;
- idempotent prior-record reuse across retries, including blocked and already-proceeded decisions;
- supervisor mirror and rehydrated handoff guarantees for blocked `escalate_resume` decisions and deadlines;
- backward compatibility of `ExecutionAdapter.apply` and its existing return shape;
- bounded outputs and exclusion of ordinary `pending_gate`, failed, and quarantined attempts.

Output only one JSON object conforming to `openspec/schemas/review-findings.schema.json`. Set `review_type` to `plan`, `target` to the change id, and `reviewer_vendor` to your vendor/model identity. Every finding must include `id`, `type`, `criticality`, `description`, `disposition`, `axis`, and `severity`; include precise `file_path`, `line_range`, and `resolution` when applicable. `description` must start with the exact marker matching severity (`Critical:`, `Nit:`, `Optional:`, `FYI:`); positive `none` findings need no marker. Critical findings must use `disposition: fix` or `escalate`. Do not edit any file.
