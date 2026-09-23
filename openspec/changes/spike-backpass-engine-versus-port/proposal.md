# Run backpass spike and record engine-versus-port decision

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `spike-backpass-engine-versus-port`
> Effort: M
> Priority: 1

## Summary

Install backpass, write a .backpassrc.json pointing memoryFiles at AGENTS.md and CLAUDE.md and skillsDir at skills/, run scan, status, and one full proposal run (never apply) against this checkout, and record the always-loaded budget bar, a per-edit evidence review of the first proposal, and a comparison of its orchestration-domain diagnostics against /improve-harness. Write the engine-versus-port decision as a capability-timeline entry in docs/decisions/.

## Dependencies

- None

## Acceptance Outcomes

- .backpassrc.json exists with memoryFiles [AGENTS.md, CLAUDE.md], skillsDir skills, and a discovery.since covering the autopilot history; .backpass/ is excluded from git via .git/info/exclude.
- A dated context-cost baseline file records the backpass budget bar (memory file plus all skill descriptions, bytes/4) alongside the /doctor figure used by skill-rightsizing ri-04.
- A review table lists every edit in the first backpass proposal with its action kind, quoted sessions, and a yes/no judgement on whether the evidence meets this repo's standard.
- The comparison of backpass orchestration-domain diagnostics against the /improve-harness report over the same window is recorded with counts of overlapping and unique findings.
- A docs/decisions/ capability-timeline entry states engine or port with the spike numbers attached, and no backpass apply was run against the shared checkout.

## Rationale

Phase 0 of the proposal. The spike costs no code and its output (budget number, instruction index, evidence rows) is needed whether the outcome is to wrap backpass as the engine or to port its concepts into collect-transcripts. Its budget bar is the harness-neutral denominator that skill-rightsizing ri-04 (record-doctor-context-cost-baseline) asks for. Every Phase 3 and Phase 4 item is shaped by this decision.
