# Add a minimal GX10 Remote Control launcher and prove it on a reference run

> Parent roadmap: `operator-front-door`
> Change ID: `add-a-minimal-gx10-remote-control-launcher-and-prove-it-on-a`
> Effort: M
> Priority: 1

## Summary

A minimal, operator-invoked launcher slice on the GX10 that, for an allowlisted repository, creates a managed worktree via the worktree skill, starts a top-level claude remote-control session in a herdr pane with the archetype's fixed permission mode, and resumes or starts autopilot. Its reference run is evidence-grounded-debugging ri-02, run end-to-end through the launcher with cross-vendor review and ending at a tiered decision rendered as a decision card.

## Dependencies

- `ri-01`
- `ri-02`

## Acceptance Outcomes

- Launching a dispatch starts a claude remote-control session in a fresh managed worktree (never the shared checkout) in a herdr pane, and the session appears in the operator's Claude app session list.
- The reference run (evidence-grounded-debugging ri-02) records sub-agent phase dispatch for its phases and zero phase_fallback_inline entries in loop-state.
- The reference run's review phase records findings from at least two vendors, and its gates are raised with a runner-computed tier and a schema-valid decision card visible in the session and on its PR.
- Invoking the launcher for a repository not on the allowlist, or with a permission mode wider than the archetype declares, is refused and logged and no process is started.

## Rationale

Top-level sessions keep the Agent tool so phases dispatch to archetypes instead of running inline; that needs neither the coordinator queue nor the governor. A thin slice proves Remote Control workers end-to-end before the queue-backed launcher (ri-09) is built on it. Operator decision: PR #690 (evidence-grounded-debugging ri-01) is decoupled from this item and is revalidated by a manual Remote Control pilot instead. Supersedes the headless-session spawn of always-on-agent-automation ri-08 for Claude archetypes.
