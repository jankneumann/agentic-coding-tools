# Tasks: Scaffold roadmap items as validating OpenSpec changes

> Change ID: `scaffold-validating-roadmap-changes`

## 1. Spec sketch generation

- [x] 1.1 Add `capability` to `RoadmapItem` (`to_dict` / `from_dict`) `[S]`
- [x] 1.2 Add `capability` to `openspec/schemas/roadmap.schema.json` `[S]`
- [x] 1.3 Verify all five existing roadmaps still validate against the schema `[S]`
- [x] 1.4 Add `_shall_sentence` and `_requirement_title` helpers `[S]`
- [x] 1.5 Add `_write_specs`, deriving requirements from `acceptance_outcomes` `[M]`
- [x] 1.6 Handle the no-outcomes case with a placeholder that still validates `[S]`
- [x] 1.7 Mark generated deltas as scaffolds naming roadmap and item `[S]`

## 2. Design sketch

- [x] 2.1 Add `_write_design`, emitted only when rationale or dependencies exist `[S]`

## 3. Wire into the scaffolder

- [x] 3.1 Call `_write_specs` and `_write_design` from `scaffold_changes` `[S]`
- [x] 3.2 Remove the bare `specs_dir.mkdir` that produced the empty directory `[S]`

## 4. Refinement phase

- [x] 4.1 `advance_to_next` enters `PLANNING` instead of `IMPLEMENTING` `[S]`
- [x] 4.2 Document why in the docstring, including the `should_skip_phase` interaction `[S]`

## 5. Tests

- [x] 5.1 `test_scaffolder_specs.py` — 12 tests covering delta emission, outcome
      mapping, modal-verb placement, double-wrap avoidance, empty-outcome fallback,
      capability defaulting and override, scaffold marking, and design emission `[M]`
- [x] 5.2 `test_specs_survive_a_commit` — real `git add`/`commit`, asserts tracked `[S]`
- [x] 5.3 `test_scaffolded_change_passes_openspec_strict` — real `openspec` CLI `[S]`
- [x] 5.4 Two `advance_to_next` tests: enters planning, and planning is not skippable `[S]`
- [x] 5.5 Confirm the new tests FAIL against the unmodified scaffolder `[S]`
- [x] 5.6 Confirm the same tests PASS against the new one — a red that is only an
      import error proves nothing `[S]`

## 6. Regression

- [x] 6.1 Roadmap suites standalone: 112 → 126 passed `[S]`
- [x] 6.2 Full CI-equivalent skills suite: 2344 passed, unchanged `[S]`
- [x] 6.3 Record why the roadmap suites cannot yet join `testpaths` `[S]`

## 7. Spec delta

- [x] 7.1 Amend "Proposal Decomposition into Roadmap Changes" to require validating
      scaffolds, outcome-derived deltas, and scaffold markers `[M]`
- [x] 7.2 Add "Roadmap items are refined before they are implemented" `[S]`
- [x] 7.3 `openspec validate --strict --all` passes `[S]`

## 8. Follow-up (not in this change)

- [ ] 8.1 Disambiguate the five flat `models.py` modules, then add
      `tests/plan-roadmap` and `tests/roadmap-runtime` to `testpaths` `[L]`
- [ ] 8.2 Teach `/plan-feature` and `/iterate-on-plan` to recognize the `SCAFFOLD`
      marker and replace rather than append `[M]`

## Migration Notes

Open tasks migrated to GitHub issues on 2026-09-02 during post-merge cleanup of
PR #350. The coordinator was unavailable (transport `none`), and this repository
tracks follow-ups as GitHub issues rather than as follow-up OpenSpec proposals.

- 8.1 → #459 (disambiguate the five flat `models.py` modules, then add the two
  roadmap suites to `testpaths`)
- 8.2 → #460 (teach `/plan-feature` and `/iterate-on-plan` to replace `SCAFFOLD`
  blocks rather than append)

Both were already scoped out of this change under "## 8. Follow-up (not in this
change)"; the issues record them so archiving does not drop them.
