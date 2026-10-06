# Publish the supervisor-worker dispatch contract

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `dispatch-contract`
> Effort: L
> Priority: 1

## Summary

Publish versioned dispatch-request and dispatch-result JSON schemas as the single definition of the supervisor-worker boundary; emit results from loop-state via runner.py emit-result; add gate provenance with posture-digest re-evaluation, execution_profile, review_requirements, degradations[], and the parked kinds permission_blocked and capability_unavailable, with a closure contract test so every schema-permitted parked shape has a supervisor answer path. Make dispatch state safe to land on a shared ref: persist only a hash of each launch token, record isolation as host-portable (repo-relative path plus host id) so another host can rebind or reinitialize live attempts, and scope auto gate dispositions to a matching roadmap_approval_ref instead of the repository-global posture.

## Dependencies

- None

## Acceptance Outcomes

- dispatch-request and dispatch-result schemas exist under openspec/schemas and execution.py and orchestrator.py validate against them with existing fixtures passing.
- runner.py emit-result produces a schema-valid result for every terminal and parked loop-state shape, verified end to end.
- A closure contract test fails when any schema-permitted parked kind/gate combination lacks a supervisor answer or resume path.
- A posture-derived gate block clears on resume after a posture change while a human rejection does not.
- execution_profile, review_requirements, and degradations[] are carried end to end, and permission_blocked and capability_unavailable parks are routed to the operator as single escalations.
- checkpoint.json stores no raw launch token (only a digest that child_start verifies) and the default secret-scan passes on a committed checkpoint with live attempts and no allowlist entry.
- A checkpoint with live attempts committed on one host can be reconciled on another host, which rebinds or reinitializes attempts instead of failing on absolute isolation paths.
- An auto disposition for proposal_approval or replan_required proceeds only for a dispatch carrying a valid roadmap_approval_ref; a standalone autopilot run without one is gated by its non-auto fallback.

## Sources of Truth

- `openspec/roadmaps/multiplayer-collaboration/supervisor-worker-contract.md` (Issues 1–4, cross-cutting transport, and the PR #662 addendum).
- Roadmap item `ri-21` in `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml` (eight acceptance outcomes above).

## Constraints

- Existing `openspec/roadmaps/*/checkpoint.json` files must keep loading: a migration or backward-compatible reader handles raw launch tokens and absolute isolation paths, with a test.
- The narrow fix on `openspec/supervise-pending-escalate-answer` (supervisor answers for `pending_gate`/`escalate_resume` parks in `skills/supervise/scripts/gate_router.py`) is merged into this branch, not re-implemented; the closure test covers it.
- Out of scope for edits: `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml`, its `checkpoint.json`, `openspec/supervise/*`, `.supervised-dispatch/`.

## Rationale

Every stall in the first supervised run occurred at an unwritten part of the supervisor-worker boundary; queue-dispatched work (team-work-queue, owner-routed-escalation, queue-dispatch-owner-acceptance) is built on it.
