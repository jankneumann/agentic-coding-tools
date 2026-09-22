# Triage merge review threads by required response

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `triage-merge-review-threads-by-required-response`
> Effort: M
> Priority: 5

## Summary

In execute_plan's delegate_comments, classify each unresolved review thread with Choice({needs_code_change, needs_reply_only, already_addressed, outdated}) over the thread text and the current diff of the file it points at, delegating only needs_code_change.

## Dependencies

- `ri-05`
- `ri-11`

## Acceptance Outcomes

- A thread whose concern is visibly resolved in the current file diff is classified already_addressed and triggers no delegation, covered by a fixture in the execute_plan tests.
- staleness_gate, security_gate and live_state_gate run before any decision call and their outcomes are unaffected, asserted by a call-ordering test.
- Threads below act_floor fall through to delegation rather than being silently closed.
- With the helper returning None every unresolved thread is delegated exactly as today, proven by existing execute_plan tests.

## Rationale

Pilot step 6 and companion section 5. Today any unresolved thread triggers delegation, so threads already addressed by a later commit or made moot by a rewrite still cost a dispatch. The surrounding staleness, security and live-state gates are facts and stay deterministic.
