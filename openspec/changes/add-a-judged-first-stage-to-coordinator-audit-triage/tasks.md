# Tasks: Add a judged first stage to coordinator audit triage

> Change ID: `add-a-judged-first-stage-to-coordinator-audit-triage`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] Add `load_capability_gap_recall_floor()` reading an optional
      `audit-triage-judgment.json` sidecar, mirroring the
      threshold-loading precedent from every prior judged item in this
      roadmap. Default floor is 0.3 (recall-oriented, not 0.5).
- [x] Add `screen_session()`: guarded `system_one_decisions` import, one
      `decide()` call per session batch asking `Noul(capability_gap)` +
      `Choice(failure_type, six enum values + "none")` +
      `Score(severity, [low, medium, high, critical])`. Degrades to
      `None` on unavailability (D1).
- [x] Wire into `drain_and_classify()`: a batch below the recall floor
      never reaches `classify_fn`; a batch at or above it still calls
      `classify_fn` unchanged, now passed a `stage_one_hint` kwarg (D3).
      `capability_gap` itself is never produced by the screen (D2).
- [x] Backfill a returned finding's missing `failure_type`/`severity`
      from `stage_one_hint` before `validate_finding` runs.
- [x] Confirm `tests/test_audit_capability_gaps.py` (25 pre-existing
      tests, including the ring-buffer hot-path latency test) passes
      unchanged.
- [x] Unit tests at `agent-coordinator/tests/test_audit_triage_judgment.py`:
      recall-floor config loading; `screen_session()`'s degradation
      branches and dict/object answer-shape handling; `drain_and_classify`'s
      below-floor no-call case, above-floor seeded-call case, hint-backfill
      case, and unavailable-screen fallback case.
- [x] Recall-rate test (`TestRecallAgainstLabeledBatches`) against a new
      small hand-labeled fixture (`tests/fixtures/audit_triage_labeled_batches.json`)
      constructed from the existing prompt's own documented detection
      patterns, recording (printing) the resulting rate (D4).
- [x] Update the `harness-engineering` capability spec's "Capability Gap
      Detection" requirement (MODIFIED), scenario "Coordinator auto-emits
      capability gaps via LLM classifier", to describe the judged screen
      and the unchanged fallback.
- [x] Roadmap completion bookkeeping (learning entry, checkpoint advance)
      in the same PR.
- [ ] Review and merge.
