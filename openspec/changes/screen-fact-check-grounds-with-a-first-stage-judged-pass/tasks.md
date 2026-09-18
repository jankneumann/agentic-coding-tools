# Tasks: Screen fact-check grounds with a first-stage judged pass

> Change ID: `screen-fact-check-grounds-with-a-first-stage-judged-pass`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] Add `load_ground_screen_confidence_floor()` reading an optional
      `fact-check-judgment.json` sidecar, mirroring
      `gatekeeper_shadow`/`triage`/`implementation_strategy_selector`/
      `vendor_review`'s threshold-loading precedent.
- [x] Add `_screen_findings()`: guarded `system_one_decisions` import, one
      batched `decide()` call with two `Noul` questions per non-protected
      finding (`ground_a_<id>`, `ground_b_<id>`). Degrades to `None` on
      unavailability.
- [x] Wire into `run()`: partition findings into protected/screenable
      (D2); screenable findings get the judged screen; a confident
      Ground-A hit removes directly; a confident Ground-B hit earns a
      seat at stage two; neither hit skips stage two entirely. Protected
      findings and (when the screen is unavailable) all findings still
      reach stage two exactly as before this item.
- [x] Preserve `run()`'s existing guard ordering (`enabled`, empty
      `findings`, `caller is None`) unchanged (D1) — verified against the
      full pre-existing test suite, not just reasoned about.
- [x] A stage-two caller failure or unparsable response discards any
      tentative stage-one work too (D3), matching the module's own
      documented "removes nothing" guarantee.
- [x] Unit tests at
      `skills/tests/parallel-infrastructure/test_fact_check_ground_screen.py`:
      threshold config loading; `_screen_findings()`'s degradation
      branches and batched-question shape; `run()`'s Ground-A-direct-removal,
      Ground-B-still-needs-evidence, zero-stage-two-calls-when-all-screen-out,
      protected-findings-never-screened, unavailable-screen-fallback, and
      stage-two-failure-discards-stage-one-work cases.
- [x] Agreement-rate test (`TestGroundAAgreementAgainstRecordedBatch`)
      against the existing labeled fixture set
      (`fixtures/review-fixtures/fact-check-transcript.json`), reproducing
      the recorded Ground-A verdicts through a stubbed screen and
      recording (printing) the resulting rate (D4).
- [x] Confirm `skills/parallel-infrastructure/scripts/tests/test_fact_check.py`
      and `skills/tests/parallel-infrastructure/test_fact_check_fixture.py`
      (34 pre-existing tests) pass unchanged.
- [x] Add an ADDED requirement to the `parallel-infrastructure` capability
      spec describing the screen (no prior requirement documented
      `fact_check.run`'s behavior at all — see proposal.md Non-Goals).
- [x] Roadmap completion bookkeeping (learning entry, checkpoint advance)
      in the same PR.
- [ ] Review and merge.
