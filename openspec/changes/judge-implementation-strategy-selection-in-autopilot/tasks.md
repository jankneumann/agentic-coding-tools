# Tasks: Judge implementation strategy selection in autopilot

> Change ID: `judge-implementation-strategy-selection-in-autopilot`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] Add `_design_section_for_package()` to `implementation_strategy_selector.py`:
      splits `design.md` on top-level headings, returns the section whose
      heading contains the package id, else `None`.
- [x] Add `load_strategy_confidence_floor()` reading an optional
      `implementation-strategy-judgment.json` sidecar, mirroring
      `gatekeeper_shadow`/`triage`'s threshold-loading precedent.
- [x] Add `_classify_package()`: guarded `system_one_decisions` import, one
      `decide()` call per package (`Choice(strategy, {alternatives,
      lead_review})`), degrades to `None` on unavailability or low
      confidence.
- [x] Wire into `select_strategies()`: `available_vendors` is passed into
      `_classify_package()`'s state as `available_vendor_count` -- judgment
      context, never a pre-judgment gate (D1, corrected mid-implementation:
      the originally scaffolded hard `len(available_vendors) < 3` ->
      `lead_review` gate does not match existing behavior and broke
      `test_fewer_than_3_vendors_reduces_score` /
      `test_boundary_score_2_selects_alternatives` when tried literally).
      Falls back to the existing `_compute_score()` sum, unmodified, when
      the judgment is unavailable.
- [x] Unit tests: design-section matching (hit/miss/no design_path);
      confidence-floor config loading; `_classify_package()` degradation
      branches; `select_strategies()`'s judged-override wiring and the
      vendor-scarcity case staying reachable via the unmodified fallback.
- [x] Confirm `test_implementation_strategy_selector.py`'s existing tests
      (including `test_fewer_than_3_vendors_reduces_score`) pass unchanged.
- [x] Update the `skill-workflow` capability spec's "Implementation
      Strategy Selection" requirement (MODIFIED) to describe the judged
      path, vendor availability as judgment context (not a gate), and the
      unchanged fallback.
- [x] Roadmap completion bookkeeping (learning entry, checkpoint advance)
      in the same PR.
- [ ] Review and merge.
