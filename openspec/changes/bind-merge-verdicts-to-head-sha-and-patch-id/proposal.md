# Bind merge verdicts to head SHA and patch-id

> Parent roadmap: `verification-enforcement-discipline`
> Change ID: `bind-merge-verdicts-to-head-sha-and-patch-id`
> Effort: L
> Priority: 1

## Summary

Record the reviewed head SHA, its `git patch-id --stable` fingerprint, and the reviewer and PR-author identities on every per-PR verdict in merge-pull-requests, and make a missing or non-eligible verdict a block unless an explicit waiver reason is recorded in merge-plan.json. Wire or delete the dead `iterate_consensus_path` staleness check.

## Dependencies

- None

## Acceptance Outcomes

- Tests using real git repositories show a verdict whose head SHA differs from the live head but whose patch-id matches is accepted, and one whose patch-id differs is rejected with a 'stale verdict' block reason.
- execution_safety never returns 'no block' for a missing or non-eligible verdict unless a waiver reason is present in merge-plan.json, and a recorded operator override path exists that is never silent.
- A verdict whose reviewer identity (vendor + session/agent id) equals the PR author identity is rejected.
- No code path reads `iterate_consensus_path` while nothing writes it, and the change extends the add-orchestrator-adjudication-review-gate structures in execution_safety.py/convergence_loop.py (declared overlap) instead of adding a parallel gate.
- merge-pull-requests SKILL.md stays line-neutral, with new guidance in references/ files.

## Rationale

Phase 1 'absence is not a pass': execution_safety.py treats a None verdict as a pass, vendor_review.py never writes head_sha, and the only staleness check is dead code, so merges can land a head nobody verified or that the author approved themselves.
