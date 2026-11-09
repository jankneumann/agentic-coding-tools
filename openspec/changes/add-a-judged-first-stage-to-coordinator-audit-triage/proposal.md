# Add a judged first stage to coordinator audit triage

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `add-a-judged-first-stage-to-coordinator-audit-triage`
> Effort: L
> Priority: 3

## Why

`audit_triage.drain_and_classify` (`agent-coordinator/src/audit_triage.py`) invokes its LLM classifier unconditionally for every drained session batch. The classifier's own prompt (`audit_triage_prompts/v1.md`) instructs it to "prefer recall over precision" — a calibration statement that a threshold on a calibrated probability expresses directly, letting most batches (which show no capability gap) skip the classifier call entirely.

## What Changes

- **MODIFIED**: `drain_and_classify` gains a first-stage judged screen (`screen_session`). One `system_one_decisions.decide()` call per session batch asks `Noul("This session shows a capability gap in the harness")`, `Choice(failure_type, the six enum values plus "none")`, and `Score(severity, [low, medium, high, critical])`.
- A batch whose capability-gap probability is below a config-held recall-oriented floor (default 0.3) never reaches the existing classifier — zero LLM calls for the common case of an ordinary session.
- A batch that clears the floor still runs the existing classifier unchanged, now passed a `stage_one_hint` (`{failure_type, severity}`) keyword argument. A returned finding missing either field is backfilled from the hint before validation, so it still passes `validate_finding` unchanged.
- `capability_gap` itself stays prose the existing classifier alone produces — the screen only decides whether to ask, and suggests labels a finding can inherit; it never invents a capability-gap description itself.
- The hot-path ring buffer (`AuditTriageBuffer.push`, `AuditService.log_operation`) is completely untouched.
- When the screen is unavailable, every batch reaches the classifier exactly as `drain_and_classify` behaved before this change.

## Impact

- Affected capability: `harness-engineering` (MODIFIED requirement: "Capability Gap Detection", scenario "Coordinator auto-emits capability gaps via LLM classifier").
- Affected code: `agent-coordinator/src/audit_triage.py` (`drain_and_classify`, new `screen_session`/`load_capability_gap_recall_floor`).
- No change to `AuditTriageBuffer`, `validate_finding`, `load_prompt`, or the classifier's own prompt template (`audit_triage_prompts/v1.md`).
- No production call site currently wires `drain_and_classify` to a live classifier (confirmed — no background task invokes it yet, per the module's own "Current Implementation Status" gaps), so this change carries zero production behavior risk today; it only changes the function's own contract and test coverage.

## Non-Goals

- Not changing `capability_gap`'s free-text nature — it stays an LLM-only field, per the parent proposal's own framing ("capability_gap is prose and must stay with an LLM").
- Not wiring a live baseline recall figure for "the current prompt" — no recorded production audit-triage batches exist to replay against yet. The recall check in this item's test suite proves the screen's wiring against a small hand-labeled synthetic fixture, not a live-model calibration (see design.md D4).
- Not installing `system-one-decisions[live]` — not installed anywhere in this repo yet (confirmed by every prior judged item), so this screen takes the unavailable-fallback branch in the standard agent-coordinator venv today, same as every other judged item.
