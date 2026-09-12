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
| skill-workflow.15 | A standalone audit writes only its run directory and the latest pointers |

This change modifies **two** canonical requirements. `Choices audit workflow
integration` gains 13 and 14 and modifies 12; its scenarios 8–11 are unchanged
and stay covered by the tests that already pin them. `Independent read-only
choices audit` is modified to widen its closed write set and gains 15 — round-1
review found that requirement still forbade writing outside
`openspec/changes/<change-id>/`, which this change's whole purpose contradicts.

## Phase 1 — Guard the skill being refactored

- [x] 1.1 Pin `prioritize-proposals`' current on-disk output with a characterization test
  **Design decisions**: D4
  **Dependencies**: none
  **Files**: `skills/tests/prioritize-proposals/test_output_characterization.py`
  **Size**: S
  Written before anything moves, and it must pass identically before and after
  the migration. Three parts (D4):
  1. **Function-level pins.** Drive a run against a `tmp_path` base and
     assert: the run directory name matches `YYYY-MM-DD-HHMMSS-<sha7>` for a
     known UTC time and head sha; `report.md` and `report.json` land inside
     it; `latest.md` and `latest.json` sit at the base; `parse_run_id` returns
     `(date, "", "legacy")` for a `<date>-legacy` name and `(date, hms, sha)`
     otherwise; and `apply_retention` moves the oldest run to
     `archive/<run-id>/` rather than deleting it. Assert the exact strings,
     not a regex that would also match a changed format.
  2. **CLI entry points as subprocesses, from a runtime-shaped layout.** Copy
     `skills/prioritize-proposals/scripts/` to
     `<tmp>/prioritize-proposals/scripts/` and `skills/shared/` to
     `<tmp>/shared/` (the shape `install.sh` produces), then run
     `python3 <tmp>/prioritize-proposals/scripts/priorities_paths.py run-id`
     (assert the output matches the run-id shape for the fixture repo's
     `HEAD`), `priorities_paths.py paths <known-id> --base <base>` (assert the
     exact `name=value` lines), and `retention.py --base <base> --retain 1`
     against a base holding two runs (assert `active=1 archived=1` and the
     archive move). `SKILL.md` itself invokes only `priorities_paths.py
     run-id` and `retention.py` — it builds the dated paths inline in bash
     (`mkdir`/`cp` against `openspec/priorities/${RUN_ID}`) and never calls the
     `paths` subcommand. Cover `paths` anyway, because the migration changes
     how every entry point in that file bootstraps its import of `shared`, and
     an entry point no caller uses today is still an entry point the move can
     break. What matters is that no existing test runs any of them as a
     subprocess: before the migration they pass trivially, after it they are
     the only thing exercising the D2 import bootstrap the way the skill's bash
     does.
  3. **Existing tests untouched.** `test_priorities_paths.py`,
     `test_retention.py` and `test_smoke_e2e.py` are not edited by this change
     — the work package's `preexisting_tests_unchanged` step enforces it.

  The subprocess run-id case must pin the timezone, not just the shape:
  invoke the CLI with `TZ` set to a non-UTC zone (`TZ=America/New_York`) and
  assert the emitted run-id matches the UTC wall clock, not local time. A shape
  assertion against live `now` still matches `YYYY-MM-DD-HHMMSS-<sha7>` if the
  CLI dropped `timezone.utc` for a naive `datetime.now()`, and the
  function-level pins call `build_run_id` with an explicit UTC datetime so they
  would not see it either.

- [x] Checkpoint: run `cd skills && uv run pytest tests/prioritize-proposals -q`, confirm green against unmodified code (the subprocess cases pass here because the copied scripts do not yet import `shared`)

## Phase 2 — Extract the shared helper

- [ ] 2.1 Write tests for `skills/shared/artifact_paths.py`
  **Design decisions**: D2, D3
  **Dependencies**: 1.1
  **Files**: `skills/tests/shared/test_artifact_paths.py`
  **Size**: S
  Import with the skills root on `sys.path`
  (`sys.path.insert(0, str(REPO_ROOT / "skills"))`, then
  `from shared.artifact_paths import ...`), which is how the package is
  reached everywhere else. Cover `build_run_id`: a known UTC datetime and sha
  produce the exact `YYYY-MM-DD-HHMMSS-<sha7>` string; a naive datetime
  raises; a sha shorter than 7 characters raises. Cover `parse_run_id` (and
  through it `RUN_ID_RE`): ids this module produces round-trip to
  `(date, hms, sha)`; the legacy `<date>-legacy` form `prioritize-proposals`
  already has on disk returns `(date, "", "legacy")`; **a collision-suffixed
  id (`2026-09-12-030000-abc1234-2`) parses and returns its suffix** — the
  un-extended regex rejects it, which would make `list_active_runs` skip
  exactly the directories D8's guard creates and let the tree grow unbounded
  while the bounding scenario still passed; a bare `<date>` returns
  `(date, "", "")`; anything else raises `ValueError`. Cover
  `apply_retention`: archive-not-delete, `retain < 1` raises, a directory
  already within the limit is untouched, `list_active_runs` skips `archive/`
  and non-run names, and `DEFAULT_RETAIN == 30`.

- [ ] 2.2 Create `skills/shared/artifact_paths.py`
  **Design decisions**: D2, D3
  **Dependencies**: 2.1
  **Files**: `skills/shared/artifact_paths.py`
  **Size**: S
  Extend `RUN_ID_RE` with an optional trailing `-<n>` group and have
  `parse_run_id` return it (D8); `prioritize-proposals` never emits a suffix,
  so accepting one costs it nothing and keeps one format shared.
  **This task is additive: copy, do not move.** Create the shared module with
  `build_run_id`, `RUN_ID_RE`, `parse_run_id`, and `apply_retention` (with
  `list_active_runs`, `RetentionResult`, `ARCHIVE_DIRNAME`) copied from
  `skills/prioritize-proposals/scripts/`, and add `DEFAULT_RETAIN = 30` (D3).
  The old definitions are removed in 3.1, the task that declares those two
  files. Deleting them here would edit files this task does not own and would
  leave the tree red at this checkpoint: `test_priorities_paths.py` and
  `test_retention.py` import those names from the old module paths, and D4
  part 3 freezes both files.
  `list_active_runs` calls the module's own `parse_run_id`. Pure functions and
  filesystem moves only — no knowledge of report or ledger filenames, per D2.
  No `sys.path` manipulation inside the shared module itself: it is imported
  as `shared.artifact_paths` by callers that put the skills root on the path
  (D2's bootstrap), never run as a script. `skills/shared/` is a declared
  shared library, so no `install-manifest.json` `cross_skill_dependencies`
  entry is added or needed.

## Phase 3 — Migrate the existing producer

- [ ] 3.1 Migrate `prioritize-proposals` onto the shared helper
  **Design decisions**: D2, D3, D4
  **Dependencies**: 2.2
  **Files**: `skills/prioritize-proposals/scripts/priorities_paths.py`, `skills/prioritize-proposals/scripts/retention.py`
  **Size**: S
  This is where 2.2's copy becomes a move: after this task **no definition**
  of `build_run_id`, `RUN_ID_RE`, `parse_run_id`, `apply_retention`,
  `list_active_runs`, `RetentionResult` or `ARCHIVE_DIRNAME` survives in
  `skills/prioritize-proposals/scripts/` — only re-exports. Grep each name
  before the checkpoint; a surviving definition is exactly the duplication D3
  exists to remove, and nothing else in the plan detects it.
  Both modules gain the D2 bootstrap
  (`sys.path.insert(0, str(Path(__file__).resolve().parents[2]))`) ahead of
  `from shared.artifact_paths import ...`. `priorities_paths.py` keeps
  `PrioritiesPaths`, `build_paths` and its CLI — the filenames are its own —
  and re-exports `build_run_id`, `RUN_ID_RE`, `parse_run_id` from the shared
  module. `retention.py` keeps its CLI entry point (default `--retain` now
  `DEFAULT_RETAIN`) and re-exports `apply_retention`, `list_active_runs`,
  `RetentionResult`, `ARCHIVE_DIRNAME`. `prioritize-proposals/SKILL.md` is
  not touched: its invocations are the CLI entry points, which do not change.
  `test_priorities_paths.py`, `test_retention.py` and `test_smoke_e2e.py` are
  not touched either — if one of them fails, the migration is wrong.

- [ ] Checkpoint: run `cd skills && uv run pytest tests/prioritize-proposals tests/shared -q`; task 1.1's characterization test must still pass unchanged, or the migration changed behavior and must be corrected rather than the test adjusted. Then `git diff --quiet "$(git merge-base HEAD main)" -- skills/tests/prioritize-proposals/test_priorities_paths.py skills/tests/prioritize-proposals/test_retention.py skills/tests/prioritize-proposals/test_smoke_e2e.py skills/prioritize-proposals/SKILL.md` must exit 0

## Phase 4 — Route the range form

- [ ] 4.1 Write tests for the destination routing
  **Spec scenarios**: skill-workflow.12, skill-workflow.13
  **Design decisions**: D1, D5, D7
  **Dependencies**: 2.2
  **Files**: `skills/tests/audit-choices/test_output_routing.py`
  **Size**: S
  Test the routing helper directly: a `range:`-prefixed recorded id returns a
  dated run directory under `openspec/choices/`; **when that directory already
  exists the helper returns a suffixed sibling** (`<run-id>-2`, then `-3`)
  rather than reusing it, and the suffixed name still satisfies
  `parse_run_id` so retention keeps counting it; **the helper rejects a name
  that exists under `<root>/archive/` as well as one that exists as an active
  run**, because retention frees the active path while the archived copy
  persists and a later audit would otherwise collide with it on the next
  retention pass (D8 — `build_run_id` resolves
  to the second, so two audits in the same UTC second at the same `HEAD` would
  otherwise share a directory and have their snapshots merged); any other id returns
  `openspec/changes/<id>/`; a change id that merely contains `..` or a colon
  but does not start with `range:` routes to the changes tree (D5 — the test is
  on the prefix of the recorded id, not on the shape of the argument). Pin D7:
  for a known `now` and `git_sha` the directory name equals
  `build_run_id(now, git_sha)` exactly, and a header `run_id` such as
  `iterate-on-implementation-2026-09-12T00:00:00Z` or the audited `head_sha`
  has no effect on it.

- [ ] 4.2 Route the range form in `run_audit.py`
  **Spec scenarios**: skill-workflow.12, skill-workflow.13
  **Design decisions**: D1, D5, D6, D7
  **Dependencies**: 4.1
  **Files**: `skills/audit-choices/scripts/run_audit.py`, `skills/audit-choices/scripts/choices_paths.py`
  **Size**: S
  Replace `run_audit.py`'s `change_dir = repo_root / "openspec" / "changes" /
  change_id` derivation with the routing helper; `collect_evidence.py`'s
  read-only derivation stays as it is (D5). `choices_paths.py` carries the D2
  bootstrap, holds the `ChoicesPaths` dataclass naming `choices.json`,
  `choices.md` and the `latest.*` pair, and calls the shared `build_run_id`
  with the driver's `resolved_now` and `resolved_git_sha` — the same two
  values `make_header` receives (D7). Order of effects on a range run: write
  the pair via `write_ledger_pair`, then `shutil.copyfile` each of the pair to
  `latest.json` / `latest.md` at `openspec/choices/` (D6). Nothing else opens
  a file for writing; the contract in 5.1 names exactly these effects plus the
  retention move 5.2 adds.

- [ ] 4.3 Extend the end-to-end test to the range destination
  **Spec scenarios**: skill-workflow.12, skill-workflow.13
  **Design decisions**: D1
  **Dependencies**: 4.2
  **Files**: `skills/tests/audit-choices/test_end_to_end.py`
  **Size**: S
  `TestStandaloneRangeInvocation` asserts the recorded `change_id`, the exit
  code, **and the ledger's location** — `test_end_to_end.py:450` reads
  `repo_root/"openspec"/"changes"/range_change_id/"choices.json"`, the exact
  path this change abolishes. That assertion is **replaced**, not
  supplemented; leaving it in place means the task cannot pass.
  Mind the entry point. The existing case drives `run_audit._cli()`, which
  passes neither `now` nor `git_sha`, so the driver resolves both internally
  and the test cannot know the run id it produced. Assertions that depend on
  those values call `run_audit.run_audit()` directly with explicit `now` and
  `git_sha` (the pattern `test_readonly_posture.py` already uses), or
  reconstruct the expected id by parsing the written header. Keep at least one
  case on `_cli()` for the exit-code contract. The same applies to the
  two-run clause below: through `_cli()` the caller cannot choose `now` and
  back-to-back runs land in the same UTC second, which exercises the collision
  guard rather than the distinct-snapshot case it means to test.
  Add: the pair lands under `openspec/choices/<run-id>/` where
  `<run-id>` is `build_run_id` of the driver's `resolved_now` and
  `resolved_git_sha` — the same values `make_header` received, never the
  header's formatted `generated_at` string (D7). Locate it by globbing
  `<run-id>*` rather than by exact name: a collision places the run at a
  `-2` sibling whose suffix no header field records (D7/D8); `latest.json` and `latest.md` are byte-equal to the run's pair (D6); no
  directory whose name contains `range:` or `..` exists anywhere under
  `openspec/changes/`; `audited_range` carries both full 40-character shas; a
  second range run over the same range at a later `now` produces a second
  directory, leaves the first byte-unchanged, gives the shared decision the
  same `stable_id` in both, and moves `latest.*` to the second (D8); and a
  change-id run in the same fixture still writes to `openspec/changes/<id>/`
  and nothing to `openspec/choices/`.

- [ ] Checkpoint: run `cd skills && uv run pytest tests/audit-choices tests/shared -q`, review diff, verify scope

## Phase 5 — Contract, retention wiring, and docs

- [ ] 5.1 Widen the read-only contract to name both destinations
  **Spec scenarios**: skill-workflow.15 (the closed write set for the range
  form), skill-workflow.12
  **Design decisions**: D6
  **Dependencies**: 4.2
  **Files**: `skills/audit-choices/SKILL.md`, `skills/tests/audit-choices/test_readonly_posture.py`, `skills/tests/audit-choices/test_skill_md.py`
  **Size**: S
  The Read-Only Contract paragraph and the matching Red Flags bullet both name
  `openspec/changes/<change-id>/choices.json` and `choices.md` today. Both gain
  the three range-form effects explicitly — the run directory's pair, the
  `latest.*` copies at `openspec/choices/`, and retention's move of older run
  directories into `openspec/choices/archive/` — a literal, checkable set, not
  a loosened rule (D6). Reword the contract's "the only writer in this skill is
  `write_ledger_pair()`" sentence per D6 (it remains the only *producer* of
  ledger content; `latest.*` are copies, retention moves directories), and add
  the range-form destination to the Output section. Add a range-form case to
  `test_writes_confined_to_ledger_pair` proving that, with fewer than
  `DEFAULT_RETAIN` runs present, such a run's working-tree diff is exactly the
  run directory's pair plus `latest.*` — nothing deleted, nothing moved.
  **Pin the wording too.** D6's argument for enumerating three effects rather
  than loosening to a rule is that the enumeration stays literal and
  checkable, but the only existing content test
  (`test_skill_md.py::test_skill_states_read_only_contract`) asserts just that
  `read-only` and `MUST NOT modify` appear — both already true today, and both
  still true if the range destination is never mentioned. The doc half of D6
  could regress or be skipped with every gate green. Add a case asserting that
  the Read-Only Contract paragraph and the Red Flags bullet each name
  `openspec/choices/` and `openspec/choices/archive/`, and that the Output
  section lists the range destination. Assert against those specific
  paragraphs, not whole-file substring presence, so a mention elsewhere in the
  file cannot satisfy it.

- [ ] 5.2 Apply retention to the standalone audit directory
  **Spec scenarios**: skill-workflow.14
  **Design decisions**: D3, D6, D8
  **Dependencies**: 2.2, 4.2
  **Files**: `skills/audit-choices/scripts/run_audit.py`, `skills/tests/audit-choices/test_output_routing.py`
  **Size**: S
  In `run_audit.py`, after the pair and `latest.*` are written on a range run,
  call the shared `apply_retention(choices_dir, retain=DEFAULT_RETAIN)` inside
  its own `try`/`except`: a failure logs a warning and the result stays
  `ok=True` with `json_path`/`md_path` set (D8). Tests: with
  `DEFAULT_RETAIN + 1` runs present, the oldest moves to
  `openspec/choices/archive/<run-id>/` with its pair intact and the working-tree
  diff is exactly the new pair, `latest.*`, and that one move (D6).
  **This case needs a deletion-aware variant of the snapshot helper.**
  `test_readonly_posture.py` asserts closure in two parts: a created-or-modified
  set equality, and separately `set(before.keys()) <= set(after.keys())` —
  nothing deleted. A retention archive move is a `shutil.move`, so it removes
  the oldest run's two files from their original keys and that second assertion
  fails. Do not relax it globally: dropping it would quietly remove the
  no-deletion guarantee from the change-id form too, and omitting the
  over-limit case from the snapshot test would leave the archive move an
  undeclared write, which is the reason D6 enumerates it. Add a variant whose
  permitted deleted set is exactly the archived run's two files and whose
  permitted created set is the new pair plus `latest.*` plus those two files
  under `openspec/choices/archive/<run-id>/`. The change-id case keeps the
  strict assertion unchanged — the two cases must not share one relaxed
  predicate.
  monkeypatch `apply_retention` to raise and assert `ok is True`, both paths
  set, the pair on disk, **and that exactly one warning naming retention was
  emitted** (caplog or captured stderr). Without that last assertion an
  implementation that swallows the failure silently passes, and the operator
  loses the only signal that the standalone-audit tree has stopped being
  bounded.

- [ ] 5.3 Document where a standalone audit writes
  **Design decisions**: D1, D8
  **Dependencies**: 4.2, 5.1
  **Files**: `docs/guides/workflow.md`, `skills/audit-choices/SKILL.md`
  **Size**: XS
  One line in the Arguments section of the skill naming the destination for the
  range form, and one bullet in the workflow guide so a reader can find a
  standalone audit's output without reading the driver. Reword the skill's
  verification step 5 ("re-run the audit over an unchanged range and confirm
  `choices.json`'s entry count and every `stable_id` are unchanged") so that
  for the range form it compares the two run directories' ledgers (D8).
  Two more places in `SKILL.md` still present in-place merge as the universal
  re-audit story and become false for the range form: the Common
  Rationalizations row saying a re-run must "update that slot in place, not
  duplicate it" via `merge_entries()`, and Step 5's "Persist idempotently"
  prose. Scope both to the change-id form and state the range form's per-run
  snapshot model beside them (D8) — the merge is not removed, it just never
  fires against a fresh dated directory.
  Depends on 5.1 because both edit `SKILL.md`.

- [ ] Checkpoint: run the four skill gates (`cd skills && bash install.sh --check`; `uv run python validate-feature/scripts/linters/dependency_direction.py --skills-root .`; `make context-refresh PYTHON=skills/.venv/bin/python`; `uv run pytest tests/ci_coverage -q`), resync runtime copies (`bash skills/install.sh --mode rsync --deps none --python-tools none`), review diff, verify scope
