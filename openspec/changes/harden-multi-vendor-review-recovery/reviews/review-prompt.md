# Plan Review — harden-multi-vendor-review-recovery (ROUND 3)

This is the THIRD and final round of multi-vendor review. The proposal has been iterated TWICE based on prior rounds:

- **Round 1** caught a fundamental architectural flaw (auto-fallback CLI subprocess shares the same buggy parser as the in-process synthesizer). User chose to drop automatic recovery and reframe as durable-checkpoint-plus-manual-recovery.
- **Round 2** caught implementation-impossibility issues (`coordination_bridge.try_emit_audit_event()` doesn't exist; criticality enum mismatch; `ConvergenceResult.synthesis_failed` is unreachable; manifest's `change_id` has no CLI source). All addressed in iteration 3.

Round 1 findings preserved in `reviews/round-1/`. Round 2 findings preserved in `reviews/round-2/`.

## What iteration 3 changed

- **Replaced coordinator audit with Python `logging.error()`** + structured payload via `extra={...}`. No new HTTP endpoint, no new bridge function. Stable strings (`convergence.synthesis_failed_with_checkpoint`, `convergence.checkpoint_write_failed`) for log filtering.
- **Dropped `synthesis_failed` field** from ConvergenceResult — three vendors converged on it being unreachable.
- **Made `change_id` OPTIONAL** in the manifest schema — removed from `required[]`, type `["string", "null"]`. CLI dispatcher writes `null`; in-process callers populate it.
- **Fixed criticality enum**: `[low, medium, high, critical]` (was `blocking`) — matches existing `openspec/schemas/review-findings.schema.json` and `consensus_synthesizer.py:181`.
- **Added second log event** `convergence.checkpoint_write_failed` for the silent-failure case where checkpoint write fails before synthesis attempt.
- **Helper now centralizes wire-format envelope construction** (review_type, target, reviewer_vendor wrapper) — callers pass raw findings list; helper builds the wrapper before writing.
- **Allowed narrow try/except around `synthesizer.synthesize()`** for the purpose of logging (was: forbidden, contradicting the audit-on-failure requirement).
- **Rewrote `contracts/README.md`** removing all stale fallback/subprocess/audit-event references.

## Your job in round 3

You're the final review pass before this proposal proceeds to IMPLEMENT. Look ESPECIALLY for:

1. **Issues introduced by iteration 3's edits** — the rewrite touched many files; were any cross-references missed? Stale text in any artifact pointing to the dropped `synthesis_failed` field? Stale references to the dropped audit event names (`convergence.fallback_recovered`, `convergence.fallback_failed`)?
2. **Logging contract correctness** — does the spec describe a logging primitive that actually works as described? Python's `logging.error(msg, extra={...})` is real, but the test for "log message contains the literal string `convergence.synthesis_failed_with_checkpoint`" is fragile to message-formatter changes. Is there a more durable test contract?
3. **Optional change_id consequences** — making the field optional fixes the dispatcher's CLI gap, but does anything downstream rely on change_id being non-null (e.g., filtering by change_id, indexing)?
4. **Atomic write completeness** — R1.S5 says manifest writes are atomic with parent-dir fsync. Per-vendor finding files use the same pattern (per task 0.2). Is the spec actually clear about that, or did I only specify it for the manifest?
5. **Path safety regex completeness** — `[A-Za-z0-9_-]+` for vendor names. Are there real vendor names this rejects? (`gpt-5-codex` and `claude_code` are compliant; what about future names with dots/version suffixes?)
6. **Helper signature consistency** — task 0.2 names parameters one way; design.md's diagram names them another way. Verify they're consistent.
7. **Anything genuinely new** — round 3 should converge to "few or no findings" if iteration 3 was correct. If you find something new and substantive, flag it.

If you find NO substantive issues — emit `"findings": []`. **Don't fabricate findings.** A clean round 3 IS the converged state.

## Read these artifacts

- `proposal.md`, `design.md`, `tasks.md`, `specs/skill-workflow/spec.md`
- `contracts/README.md`, `contracts/review-cache-layout.schema.json`, `contracts/finding.schema.json`
- `work-packages.yaml`

Existing files referenced:
- `skills/autopilot/scripts/convergence_loop.py`
- `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`
- `skills/parallel-infrastructure/scripts/review_dispatcher.py`
- `openspec/schemas/review-findings.schema.json` (for criticality enum reference)

## Output format

Wrapper-object JSON (the wire format the synthesizer reads):

```json
{
  "review_type": "plan",
  "target": "harden-multi-vendor-review-recovery",
  "reviewer_vendor": "<your vendor>",
  "findings": [...]
}
```

Each finding has `id`, `type` (architecture | security | spec_gap | correctness | contract_mismatch | testability | observability | performance | resilience | compatibility | style), `criticality` (low | medium | high | critical), `description`, `disposition` (fix | regenerate | accept | escalate), `resolution`, `file_path` (optional), `line_range` (optional, as `{"start": N, "end": M}` or null), `vendor`.
