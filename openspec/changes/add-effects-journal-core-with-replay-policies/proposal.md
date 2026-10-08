# Add effects journal core with replay policies

> Parent roadmap: `durable-execution`
> Change ID: `add-effects-journal-core-with-replay-policies`
> Effort: M
> Priority: 1

## Summary

Add a shared append-only effects journal helper (skills/shared/effects_journal.py) exposing begin, complete, fail, and resolve_interrupted over openspec/changes/<change-id>/effects.jsonl, with deterministic idempotency keys derived from (change_id, phase, transition_sequence, effect_kind, target) and per-effect-kind replay policies (replayable, verify_then_skip, never_replay). Register the journal in docs/guides/state-artifacts.md and document the supervisor application_journal as its first specialized instance.

## Dependencies

- None

## Acceptance Outcomes

- A fault-injection test killing the process between started and completed shows replayable re-runs once, verify_then_skip probes and records completed without a second side effect, and never_replay parks the change with a named escalation and performs no action.
- Idempotency keys are identical across two runs with the same inputs and contain no wall-clock-dependent component.
- The journal works with the coordinator unreachable; any coordinator copy is an optional persist-first projection never written back into the journal.
- docs/guides/state-artifacts.md lists the effects journal with holder, writer, authority, consumers, and missing/stale behavior, scoped to "did this effect happen?" only.
- Journal entries are bounded in size and store results (PR URL, commit SHA), never transcripts.

## Rationale

Phase 1 safety foundation; every other capability (resumable phases, cascading abort, durable executor mapping) relies on a durable record of whether an irreversible action already happened, so the never-repeat-silently guarantee must exist first.
