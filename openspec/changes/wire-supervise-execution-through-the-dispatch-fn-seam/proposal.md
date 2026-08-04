# Wire supervise execution through the dispatch_fn seam

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `wire-supervise-execution-through-the-dispatch-fn-seam`
> Effort: L
> Priority: 1

## Summary

Fill `autopilot-roadmap/scripts/orchestrator.py`'s `dispatch_fn(item_id, phase, context)` seam from the supervise skill, dispatching each `/autopilot` run as a background sub-agent in its own managed worktree, with fan-out for multiple concurrent changes whose file scopes are disjoint.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- A supervise session drives a roadmap item through its autopilot phase machine via dispatch_fn with each phase run executing as a background sub-agent in its own worktree.
- Two roadmap items with disjoint file scopes progress concurrently from one supervisor session, each in its own worktree.
- The supervisor session context contains dispatch outcomes but not sub-agent transcripts, verified by inspecting the session after a two-item run.

## Rationale

Execution is the supervise skill's core verb; dispatching runs as background sub-agents keeps outcomes rather than transcripts in the supervisor's context and enables concurrent progress from one session.
