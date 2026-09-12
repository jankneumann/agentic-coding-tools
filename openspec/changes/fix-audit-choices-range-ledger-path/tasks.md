# Tasks: fix-audit-choices-range-ledger-path

Selected approach: extract the run-id format to `skills/shared/`, migrate
`prioritize-proposals` onto it without changing its output, then route the
`audit-choices` range form to a run-scoped directory.

Test tasks come before the implementation they verify. Design decisions `D<n>`
refer to this change's `design.md`.

## Scenario key

| Ordinal | Scenario |
|---------|----------|
| skill-workflow.12 | Standalone invocation against a commit range |
| skill-workflow.13 | A change-id audit is unaffected by the range-form destination |
| skill-workflow.14 | Standalone audit output is bounded |

Scenarios 8–11 in the modified requirement are unchanged by this change and
stay covered by the tests that already pin them.

## Phase 1 — Guard the skill being refactored

- [ ] 1.1 Pin `prioritize-proposals`' current on-disk output with a characterization test
  **Design decisions**: D4
  **Dependencies**: none
  **Files**: `skills/tests/prioritize-proposals/test_output_characterization.py`
  **Size**: S
  Written before anything moves, and it must pass identically before and after
  the migration. Drive a run against a `tmp_path` base and assert: the run
  directory name matches `YYYY-MM-DD-HHMMSS-<sha7>` for a known UTC time and
  head sha; `report.md` and `report.json` land inside it; `latest.md` and
  `latest.json` sit at the base; and `apply_retention` moves the oldest run to
  `archive/<run-id>/` rather than deleting it. Assert the exact strings, not a
  regex that would also match a changed format.

- [ ] Checkpoint: run `cd skills && uv run pytest tests/prioritize-proposals -q`, confirm green against unmodified code

## Phase 2 — Extract the shared helper

- [ ] 2.1 Write tests for `skills/shared/artifact_paths.py`
  **Design decisions**: D2, D3
  **Dependencies**: 1.1
  **Files**: `skills/tests/shared/test_artifact_paths.py`
  **Size**: S
  Cover `build_run_id`: a known UTC datetime and sha produce the exact
  `YYYY-MM-DD-HHMMSS-<sha7>` string; a naive datetime raises; a sha shorter
  than 7 characters raises. Cover `RUN_ID_RE`: it parses ids this module
  produces, and the legacy `<date>-legacy` and bare `<date>` forms
  `prioritize-proposals` already has on disk. Cover `apply_retention`:
  archive-not-delete, `retain < 1` raises, and a directory already within the
  limit is untouched.

- [ ] 2.2 Create `skills/shared/artifact_paths.py`
  **Design decisions**: D2, D3
  **Dependencies**: 2.1
  **Files**: `skills/shared/artifact_paths.py`
  **Size**: S
  Move `build_run_id`, `RUN_ID_RE`, and `apply_retention` (with its
  `list_active_runs` helper and `RetentionResult`) from
  `skills/prioritize-proposals/scripts/`. Pure functions and filesystem moves
  only — no knowledge of report or ledger filenames, per D2. `skills/shared/`
  is a declared shared library, so no `install-manifest.json`
  `cross_skill_dependencies` entry is added or needed.

## Phase 3 — Migrate the existing producer

- [ ] 3.1 Migrate `prioritize-proposals` onto the shared helper
  **Design decisions**: D2, D3, D4
  **Dependencies**: 2.2
  **Files**: `skills/prioritize-proposals/scripts/priorities_paths.py`, `skills/prioritize-proposals/scripts/retention.py`, `skills/prioritize-proposals/SKILL.md`
  **Size**: S
  `priorities_paths.py` keeps `PrioritiesPaths` and `build_paths` — the
  filenames are its own — and imports `build_run_id`/`RUN_ID_RE` from the
  shared module. `retention.py` keeps its CLI entry point and delegates to the
  shared `apply_retention`. Update any SKILL.md line that names the moved
  functions by path.

- [ ] Checkpoint: run `cd skills && uv run pytest tests/prioritize-proposals tests/shared -q`; task 1.1's characterization test must still pass unchanged, or the migration changed behavior and must be corrected rather than the test adjusted

## Phase 4 — Route the range form

- [ ] 4.1 Write tests for the destination routing
  **Spec scenarios**: skill-workflow.12, skill-workflow.13
  **Design decisions**: D1, D5
  **Dependencies**: 2.2
  **Files**: `skills/tests/audit-choices/test_output_routing.py`
  **Size**: S
  Test the routing helper directly: a `range:`-prefixed recorded id returns a
  dated run directory under `openspec/choices/`; any other id returns
  `openspec/changes/<id>/`; a change id that merely contains `..` or a colon
  but does not start with `range:` routes to the changes tree (D5 — the test is
  on the prefix of the recorded id, not on the shape of the argument).

- [ ] 4.2 Route the range form in `run_audit.py`
  **Spec scenarios**: skill-workflow.12, skill-workflow.13
  **Design decisions**: D1, D5
  **Dependencies**: 4.1
  **Files**: `skills/audit-choices/scripts/run_audit.py`, `skills/audit-choices/scripts/choices_paths.py`
  **Size**: S
  Replace the single `change_dir = repo_root / "openspec" / "changes" /
  change_id` derivation with the routing helper. `choices_paths.py` holds the
  `ChoicesPaths` dataclass naming `choices.json`, `choices.md` and the
  `latest.*` pair, and calls the shared `build_run_id`. Write `latest.json` and
  `latest.md` at `openspec/choices/` on every range run. Open no file for
  writing outside `choices_ledger.write_ledger_pair` and the `latest.*`
  rewrite, which the contract in 5.1 must then name.

- [ ] 4.3 Extend the end-to-end test to the range destination
  **Spec scenarios**: skill-workflow.12, skill-workflow.13
  **Design decisions**: D1
  **Dependencies**: 4.2
  **Files**: `skills/tests/audit-choices/test_end_to_end.py`
  **Size**: S
  `TestStandaloneRangeInvocation` currently asserts the recorded `change_id`
  and exit code. Add: the pair lands under `openspec/choices/<run-id>/`; no
  directory whose name contains `range:` or `..` exists anywhere under
  `openspec/changes/`; `audited_range` carries both full 40-character shas; and
  a change-id run in the same fixture still writes to
  `openspec/changes/<id>/` and nothing to `openspec/choices/`.

- [ ] Checkpoint: run `cd skills && uv run pytest tests/audit-choices tests/shared -q`, review diff, verify scope

## Phase 5 — Contract, retention wiring, and docs

- [ ] 5.1 Widen the read-only contract to name both destinations
  **Spec scenarios**: skill-workflow.12
  **Design decisions**: D6
  **Dependencies**: 4.2
  **Files**: `skills/audit-choices/SKILL.md`, `skills/tests/audit-choices/test_readonly_posture.py`
  **Size**: S
  The Read-Only Contract paragraph and the matching Red Flags bullet both name
  `openspec/changes/<change-id>/choices.json` and `choices.md` today. Both gain
  the range-form destination and the `latest.*` pair explicitly — a literal,
  checkable set, not a loosened rule (D6). Add a range-form case to
  `test_writes_confined_to_ledger_pair` proving such a run's working-tree diff
  is exactly the run directory's pair plus `latest.*`.

- [ ] 5.2 Apply retention to the standalone audit directory
  **Spec scenarios**: skill-workflow.14
  **Design decisions**: D3
  **Dependencies**: 2.2, 4.2
  **Files**: `skills/audit-choices/scripts/choices_paths.py`, `skills/tests/audit-choices/test_output_routing.py`
  **Size**: S
  Call the shared `apply_retention` against `openspec/choices/` after a range
  run, with the same default retain count `prioritize-proposals` uses. Assert
  archive-not-delete: the oldest run moves to `openspec/choices/archive/<run-id>/`
  with its ledger pair intact.

- [ ] 5.3 Document where a standalone audit writes
  **Dependencies**: 4.2
  **Files**: `docs/guides/workflow.md`, `skills/audit-choices/SKILL.md`
  **Size**: XS
  One line in the Arguments section of the skill naming the destination for the
  range form, and one bullet in the workflow guide so a reader can find a
  standalone audit's output without reading the driver.

- [ ] Checkpoint: run the four skill gates (`cd skills && bash install.sh --check`; `uv run python validate-feature/scripts/linters/dependency_direction.py --skills-root .`; `make context-refresh PYTHON=skills/.venv/bin/python`; `uv run pytest tests/ci_coverage -q`), resync runtime copies (`bash skills/install.sh --mode rsync --deps none --python-tools none`), review diff, verify scope
