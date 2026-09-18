# Tasks: Judge implementation strategy selection in autopilot

> Change ID: `judge-implementation-strategy-selection-in-autopilot`

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Tasks

- [ ] Add `_design_section_for_package()` to `implementation_strategy_selector.py`:
      splits `design.md` on top-level headings, returns the section whose
      heading contains the package id, else `None`.
- [ ] Add `load_strategy_confidence_floor()` reading an optional
      `implementation-strategy-judgment.json` sidecar, mirroring
      `gatekeeper_shadow`/`triage`'s threshold-loading precedent.
- [ ] Add `_classify_package()`: guarded `system_one_decisions` import, one
      `decide()` call per package (`Choice(strategy, {alternatives,
      lead_review})`), degrades to `None` on unavailability or low
      confidence.
- [ ] Wire into `select_strategies()`: `len(available_vendors) < 3` ->
      `lead_review` before any judgment attempt (D1); otherwise try the
      judgment; fall back to the existing `_compute_score()` sum unchanged.
- [ ] Unit tests: design-section matching (hit/miss/no design_path);
      confidence-floor config loading; `_classify_package()` degradation
      branches; `select_strategies()` vendor-floor short-circuit and
      judged-override wiring.
- [ ] Confirm `test_implementation_strategy_selector.py`'s existing tests
      (including `test_fewer_than_3_vendors_reduces_score`) pass unchanged.
- [ ] Update the `skill-workflow` capability spec's "Implementation
      Strategy Selection" requirement (MODIFIED) to describe the judged
      path, the vendor floor, and the unchanged fallback.
- [ ] Roadmap completion bookkeeping (learning entry, checkpoint advance)
      in the same PR.
- [ ] Review and merge.
