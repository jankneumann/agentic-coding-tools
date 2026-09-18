# Tasks: Judge decision-tag backfill in explore-feature

> Change ID: `judge-decision-tag-backfill-in-explore-feature`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] Add `_answer_field()` and guarded `system_one_decisions` import to
      `backfill_decision_tags.py`.
- [x] Add `_classify_phase_decisions()`: one batched `decide()` call per
      session-log phase, one `Choice(capability, keyword_map's tags +
      "none")` question per decision keyed by `decision_index` (D1).
      Criteria derived from `keyword_map`'s own keys, not hardcoded (D2).
      Degrades per-decision on a malformed/missing individual answer, and
      whole-phase on total unavailability (D3).
- [x] Wire into `propose_tags_for_archive()`: group extracted decisions by
      `(phase_name, phase_date)`, classify each phase's batch, use the
      judged result when present, otherwise fall back to `classify_decision`
      unchanged. A `"none"` choice sets `proposed_capability=None` directly
      (D4), not via the fallback path.
- [x] Confirm `skills/explore-feature/tests/test_backfill_decision_tags.py`
      (11 pre-existing tests) passes unchanged.
- [x] Unit tests at
      `skills/tests/explore-feature/test_backfill_decision_tags_judgment.py`:
      `_classify_phase_decisions()`'s batched-question shape and
      degradation branches (whole-batch, per-decision, "none" mapping);
      `propose_tags_for_archive()`'s single-call-per-phase wiring,
      judged-choice population, none-excluded-from-edits, and
      unavailable-judgment fallback.
- [x] `uv run ruff check .` clean (learned from `ri-16`: verify before
      pushing, not after CI catches it).
- [x] Add an ADDED requirement to a new `explore-feature` capability spec
      describing the judged classification (no capability spec previously
      existed for this skill at all — see proposal.md Non-Goals).
- [x] Roadmap completion bookkeeping (learning entry, checkpoint advance)
      in the same PR.
- [ ] Review and merge.
