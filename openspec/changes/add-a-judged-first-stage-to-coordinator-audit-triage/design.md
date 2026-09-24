# Design: Add a judged first stage to coordinator audit triage

## Context

`drain_and_classify` calls its LLM classifier once per drained `(agent_id, session_id)` batch, unconditionally. This item inserts a cheap first-stage judged screen ahead of that call, mirroring the two-stage shape already used by `screen-fact-check-grounds-with-a-first-stage-judged-pass` (ri-15) for the same reason: the existing prompt's own "prefer recall over precision" instruction is a calibration statement a probability threshold can express directly.

## Decisions

### D1: The screen is per-batch, not batched across sessions

Unlike ri-15's fact-check screen (which batches many findings' questions into one `decide()` call because they share one packet diff), `drain_and_classify` already loops over independent `(agent_id, session_id)` batches with no shared context between them. The roadmap item's own wording ("ask **per session batch** Noul(...)") matches this: one `screen_session()` call per batch, at the same point in the loop the classifier call used to be unconditional.

### D2: `capability_gap` stays exclusively an LLM (stage-two) field

The parent roadmap item is explicit: "capability_gap is prose and must stay with an LLM, which makes this the two-stage shape." The screen never produces a `capability_gap` value — only a probability, a suggested `failure_type`, and a suggested `severity`. A finding's `capability_gap` text always comes from the existing classifier when it runs.

### D3: Seeding backfills only the two labels a Noul/Choice/Score screen can produce

"Stage-two findings are seeded with the stage-one failure_type and severity and still pass `validate_finding` unchanged" is implemented as: the screen's suggested `failure_type`/`severity` are passed to `classify_fn` as a `stage_one_hint` keyword argument (so a classifier prompt that chooses to use it can), and separately, any returned finding missing either field is backfilled from the hint before `validate_finding` runs. This is additive only — a `classify_fn` that ignores the new kwarg, or already returns both fields itself, behaves identically to before this item (verified: all 25 pre-existing tests in `test_audit_capability_gaps.py` pass unchanged, none of which pass or expect `stage_one_hint`).

### D4: The "recall" acceptance outcome is a wiring test, not a live-calibration claim

No `[live]` extra is installed anywhere in this repo (confirmed identically by `ri-09`, `ri-10`, `ri-11`, `ri-15`), and unlike ri-15's fact-check screen, no recorded production audit-triage batches exist to replay at all. `TestRecallAgainstLabeledBatches` uses a small, hand-labeled synthetic fixture (`tests/fixtures/audit_triage_labeled_batches.json`, 5 batches, 3 true/2 false) constructed directly from the existing prompt's own documented detection patterns (lock contention, guardrail-violation-then-profile-denial, repeated failed `complete_task`). It proves the screen's wiring reproduces those labels when given an answer set that agrees with them, and records both the screen's recall and the "current prompt" baseline (1.0, by the fixture's own construction) for visibility — a genuine live-model recall figure is deferred to a future validation-phase run against real recorded batches, mirroring `ri-15`'s own precedent for a parallel gap.

### D5: No production caller exists yet, so this item carries zero live-behavior risk

Confirmed by a repo-wide search: nothing in `agent-coordinator/src/` currently calls `drain_and_classify` outside test files — the background task that would drain the buffer on a cadence is not yet wired up (per the module's own "Current Implementation Status" list). The new `stage_one_hint` keyword-only parameter on `classify_fn`'s call is therefore purely additive today.

## Non-goals

- Changing `AuditTriageBuffer`, `validate_finding`, `load_prompt`, or the classifier's own prompt template.
- A live TypeSafe SDK installation (see D4 and the parent proposal's Non-Goals).
