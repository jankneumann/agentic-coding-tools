# Tasks: Judge fix-tier classification in fix-scrub

> Change ID: `judge-fix-tier-classification-in-fix-scrub`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] Add `_answer_field()` and guarded `system_one_decisions` import to
      `classify.py`.
- [x] Add `_judge_fix_tier_gates(findings, dry_run=False)`: one batched
      `decide()` call per `classify()` invocation, one `Noul` question per
      `markers`/`deferred:*` finding (D1/D2). Returns `dict[int, bool]`
      covering only findings with a usable answer -- missing/malformed
      answers fall back per-finding, whole-batch unavailability falls back
      for all (D5).
- [x] Add `classify_finding(finding, judged_hint: bool | None = None)`:
      `judged_hint` overrides `_marker_has_sufficient_context` /
      `_deferred_has_proposed_fix` when not `None` (D3). Default `None`
      keeps every existing call site and test unchanged.
- [x] Wire `classify()` to compute the batch via `_judge_fix_tier_gates` after
      severity filtering, then pass each finding's result into
      `classify_finding`.
- [x] `DEFAULT_FIX_TIER_NOUL_THRESHOLD = 0.5` module constant (D4 -- no
      config-loadable floor for this item).
- [x] Confirm `skills/fix-scrub/tests/test_classify.py` (32 pre-existing
      tests) passes unchanged.
- [x] Unit tests at `skills/fix-scrub/tests/test_classify_judgment.py` (D7 --
      corrected location, not `skills/tests/fix-scrub`): batched-question
      shape and call-count for non-judgeable sources; degradation branches
      (whole-batch, per-finding); the ten-word-unactionable vs
      terse-actionable marker case from the acceptance outcome; deferred
      concrete-fix judgment.
- [x] `uv run ruff check .` clean before push (ri-16 lesson).
- [x] Add an ADDED requirement to a new `fix-scrub` capability spec
      describing the judged classification (no capability spec previously
      existed for this skill -- see proposal.md).
- [ ] Roadmap completion bookkeeping (learning entry, checkpoint advance,
      `item.status = COMPLETED` on the roadmap item) in the same PR.
- [ ] Review and merge.
