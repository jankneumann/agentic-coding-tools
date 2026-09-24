# Tasks: Judge multi-vendor review eligibility for pull requests

> Change ID: `judge-multi-vendor-review-eligibility-for-pull-requests`

## Status

- [x] Planning
- [x] Implementation
- [x] Testing
- [ ] Review
- [ ] Done

## Tasks

- [x] Extend `compute_pr_size()` to fetch `title`/`body` (cheap metadata,
      not the diff) alongside the existing additions/deletions.
- [x] Add `load_vendor_review_thresholds()` reading an optional
      `vendor-review-judgment.json` sidecar, mirroring
      `gatekeeper_shadow`/`triage`/`implementation_strategy_selector`'s
      threshold-loading precedent. Covers `max_changed_lines`, `max_files`,
      and `confidence_floor` in one file.
- [x] Add `_classify_pr_risk()`: guarded `system_one_decisions` import, one
      `decide()` call asking `Noul(warrants_review)` + `Score(risk, [...])`
      over title/body/file list/diff stat. Degrades to `None` on
      unavailability. Eligibility is `noul >= confidence_floor` (mirroring
      `triage.py`'s bare-Noul convention — no separate confidence field on
      a Noul per the parent proposal's typed contract).
- [x] Wire into `check_review_eligibility()`: deterministic `is_draft` and
      `SKIP_ORIGINS` checks run first and never invoke the judgment (D1);
      the judged path, when available, replaces the size check but still
      falls through into the existing `has_approval`/`changes_requested`
      check before returning eligible (D2) — that check stays independent
      of risk. Falls back to the existing size-threshold rule, reading
      thresholds from config, when the judgment is unavailable.
- [x] Unit tests at `skills/tests/merge-pull-requests/test_vendor_review_judgment.py`:
      threshold config loading; `_classify_pr_risk()`'s degradation
      branches and state shape (no diff, title/body/files present); the
      draft/origin call-count guards; judged-eligible-despite-small and
      judged-ineligible-despite-large cases; the existing-approval override;
      the unavailable-judgment fallback for both small and large PRs.
- [x] Confirm the full `merge-pull-requests` test suite (both
      `skills/tests/merge-pull-requests/` and
      `skills/merge-pull-requests/scripts/tests/`) passes unchanged (435
      tests).
- [x] Update the `merge-pull-requests` capability spec's "Vendor Review
      Artifact Resilience" requirement (MODIFIED) to describe the judged
      path, the deterministic skips that precede it, and the unchanged
      fallback and existing-approval override.
- [x] Roadmap completion bookkeeping (learning entry, checkpoint advance)
      in the same PR.
- [ ] Review and merge.
