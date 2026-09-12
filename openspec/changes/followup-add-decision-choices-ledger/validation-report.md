# Validation Report: followup-add-decision-choices-ledger

**Date**: 2026-09-11
**Commit**: e649daae
**Branch**: openspec/followup-add-decision-choices-ledger--val2 (parent: openspec/followup-add-decision-choices-ledger)

## Why This Is a Rerun

A prior validation pass (commit `a481fb89`, handoff `validate-aadfeb07.json`)
returned **FAIL** — not on a behavioral defect, but on nominal spec coverage:
scenario `skill-workflow.11` ("Absent or empty ledger is silent at the
gates") requires the two empty-case branches at each gate to be
*distinguishable*, and the only test pinning that distinguishability
(`test_both_empty_case_wordings_present`) merely asserted both wording
strings appear somewhere in the section — a passing test even if the
branches were swapped. `validate-feature`'s zero-needs-user branch had the
same gap.

Commit `e649daae` ("test(audit-choices): make scenario 11's coverage real,
not nominal") adds two parametrized executable tests —
`TestCleanupFeatureStep5_5::test_step_5_5_branch_selection` (3 cases: absent,
empty-entries, open-entry) and `TestValidateFeatureChoicesRow::test_choices_row_branch_selection`
(4 cases: absent, empty-entries, one-needs-user, entries-none-open) — that
extract the actual shipped bash fence from each SKILL.md and execute it
against real fixtures, then assert on the produced output. It also fixes a
stale wording nit in `design.md`'s F8 (see below).

## Independent Verification of the Fix (mutation test)

I did not accept the new tests at face value. I manually swapped the two
empty-case branches in both shipped hooks and re-ran the full suite, to
confirm the new tests actually discriminate a regression rather than being
executable-but-still-nominal:

- **`skills/cleanup-feature/SKILL.md` Step 5.5**: swapped which branch prints
  `"no choices ledger"` vs `"no open choices"` (absent-file branch now prints
  `"no open choices"`, present-but-empty branch now prints `"no choices
  ledger"`).
- **`skills/validate-feature/SKILL.md` Step 11**: swapped which branch sets
  `CHOICES_ROW` to `"○ Choices: no ledger"` vs `"✓ Choices: 0 needs-user"`
  (absent-ledger branch now emits the zero-needs-user row and vice versa).

Result with both files mutated: `uv run pytest tests/audit-choices -q` →
**6 failed, 127 passed**. The failures were exactly the ones a real
regression should produce:
- `TestValidateFeatureChoicesRow::test_choices_row_branch_selection[absent]`
- `TestValidateFeatureChoicesRow::test_choices_row_branch_selection[empty-entries]`
- `TestValidateFeatureChoicesRow::test_choices_row_branch_selection[entries-none-open]`
- `TestCleanupFeatureStep5_5::test_step_5_5_branch_selection[absent-ledger]`
- `TestCleanupFeatureStep5_5::test_step_5_5_branch_selection[empty-ledger]`
- `TestValidateFeatureChoicesRow::test_no_ledger_path_survives_set_u` (a
  pre-existing test, also caught by this mutation since it checks for the
  literal `"no ledger"` wording)

Meanwhile `test_both_empty_case_wordings_present` (the old string-presence
test that produced the FAIL last round) **still passed** under the mutation
— confirming it really is blind to a branch swap, and confirming the
mutation was a fair test of the fix rather than a strawman.

I then restored both files with `git checkout --` (never `git stash`) and
re-ran the suite: **133 passed**, `git diff --stat` empty, working tree
identical to HEAD. This matches the fix commit's own stated verification
("five of the new parametrized cases fail, while the old string-presence
test still passes") — independently reproduced, not merely trusted because
the commit message said so.

**Conclusion: the gap the previous pass identified is genuinely closed.**
Scenario `skill-workflow.11`'s distinguishability property is now proven by
execution against real fixtures at both gates, for all branch combinations,
not by string-presence alone.

## Spec Compliance

- **Status**: pass

All five scenarios in the change's `skill-workflow` delta (`skill-workflow.8`
through `.12`) have real, executable coverage of every branch they turn on;
the per-scenario assessment below records the test behind each one. Task
checkbox drift: 0 unchecked items in `tasks.md`. `openspec validate
followup-add-decision-choices-ledger --strict` passes. Four quality gates
pass at expected counts: 133 `tests/audit-choices`, 124 `tests/ci_coverage`,
`install.sh --check`, and the dependency-direction linter.

## Smoke Tests

- **Status**: not applicable

No deployable surface. `classify_deployable_surface` returns
`deployable=False`: the change adds one read-only Python script and edits
skill-instruction Markdown, documentation and tests. No containers were
started, which is the correct outcome and not a skipped check.

## Security

- **Status**: not applicable

No running service to scan. The one script added opens no file for writing
and is pinned as read-only by
`skills/tests/audit-choices/test_readonly_posture.py`.

## E2E Tests

- **Status**: not applicable

No frontend or live service surface.

## Change Shape

No deployable surface. `git diff --name-only main...HEAD` touches only
`openspec/changes/followup-add-decision-choices-ledger/**`,
`skills/audit-choices/{SKILL.md,scripts/needs_user.py}`,
`skills/{cleanup-feature,validate-feature,iterate-on-implementation}/SKILL.md`,
`skills/explore-feature/scripts/decision_index.py`, `skills/install-manifest.json`,
`skills/tests/audit-choices/{test_end_to_end.py,test_needs_user.py,test_workflow_hooks.py}`,
and `docs/guides/workflow.md`/`docs/decisions/README.md` — one read-only
Python script plus skill-instruction Markdown, docs and tests. Deploy, Smoke,
Gen-Eval and E2E are therefore **N/A**, not skipped. No containers or podman
socket were started for this validation.

## Phase Results

✓ Quality Gates: all four required gates pass, matching the expected counts
  - `cd skills && uv run pytest tests/audit-choices -q` → **133 passed**
    (126 baseline + 7 new: 4 in `TestValidateFeatureChoicesRow`, 3 in
    `TestCleanupFeatureStep5_5`)
  - `cd skills && bash install.sh --check` → "Skill install portability validation passed"
  - `cd skills && uv run python validate-feature/scripts/linters/dependency_direction.py --skills-root .` → "Dependency-direction validation passed"
  - `cd skills && uv run pytest tests/ci_coverage -q` → **124 passed**
- `openspec validate followup-add-decision-choices-ledger --strict` → "Change 'followup-add-decision-choices-ledger' is valid"

○ `make context-refresh` (pre-existing, out of scope): fails repo-wide with
  ~30 unrelated active OpenSpec changes showing pending spec merges. Reran it
  and confirmed `spec:skill-workflow` still appears among the failures (3
  occurrences in the output) — expected, since this change's delta merges
  into `openspec/specs/skill-workflow/spec.md` only at archive time. None of
  the failing `validation_id`s correspond to files this diff touches.

○ Test collection (pre-existing, out of scope): `tests/roadmap-runtime` and
  `tests/project-context-refresh` still fail to collect with the same
  `ImportError: cannot import name 'LearningEntry'/'Checkpoint'/'Effort' from
  'models'` errors. Confirmed none of the files in this diff touch
  `project-context-runtime/scripts/models.py`, `roadmap-runtime/`, or
  `project-context-refresh/`.

✓ Tasks: every task and checkpoint in `tasks.md` (3.0–3.7, both checkpoints)
  is checked `[x]`, re-verified against shipped code:
  - 3.0 → `skills/audit-choices/scripts/needs_user.py` + `test_needs_user.py`
  - 3.1 → `iterate-on-implementation/SKILL.md` Step 11.5 — confirmed present:
    not-gated-by-`VENDOR_REVIEW` first line, both tracked (`git checkout --`)
    and untracked (`rm -f`) orphan-discard branches, `Choices audit:` line in
    Step 12 summary
  - 3.2 → `validate-feature/SKILL.md` Step 11 sketch + Step 12 heredoc both
    carry the `Choices:` row; no `## Choices` heading anywhere in the file
    (`grep -n "^##* .*Choices"` → no match)
  - 3.3 → `cleanup-feature/SKILL.md` Step 5.5 inserted before Step 6; Step
    5a's early exit retargeted from "skip to Step 6" to "skip to Step 5.5"
  - 3.4 → `docs/guides/workflow.md` command-ladder line and infrastructure-
    skill bullet
  - 3.5 → `decision_index.py::emit_readme` "Related: the choices ledger"
    paragraph, `docs/decisions/README.md` regenerated in the same commit
  - 3.6 → `test_end_to_end.py`
  - 3.7 → `test_workflow_hooks.py`, now including the two new branch-
    selection test classes

✓ Spec Compliance / Design Decisions F1–F8: **PASS** — see below.

## Spec Compliance — per-scenario assessment

Re-assessed on this HEAD's own terms, not copied from the prior report.

### skill-workflow.8 — Workflow invocation is non-blocking
**REAL.** `TestIterateOnImplementationStep11_5` extracts the actual Step
11.5 bash/python text and executes it against real git fixtures: F2's
entries/schema_version comparison, partial-pair orphan discard for both
untracked-first-audit and tracked-truncated shapes, the dispatch-failed
early-return path, a failing `git commit` leaving nothing staged, a failing
`git checkout --` on the unchanged path, and stale-half detection via
`generated_at` mismatch. Unchanged from the prior pass and confirmed still
present and passing.

### skill-workflow.9 — needs-user entries surface at the validation gate
**REAL.** `test_worktree_shaped_env_still_finds_the_ledger` and
`test_choices_row_branch_selection[one-needs-user]` both extract the real
Step 11 snippet and run it against a genuine `choices.json` with an open
`needs-user` entry, asserting the exact `⚠ Choices: 1 needs-user entries
(choices.md)` row and the entry's `stable_id`. Ordering/formatting is proven
independently in `test_needs_user.py::TestMixedLedger`.

### skill-workflow.10 — needs-user entries surface at the cleanup gate
**REAL — this scenario's coverage gap is now closed.**
`test_step_5_5_branch_selection[open-entry]` extracts the real Step 5.5 bash
block and runs it against a fixture with one open `needs-user` entry,
asserting the entry's `stable_id` appears and the empty-case wording does
not leak in. Combined with the reader's own tests (shared with 3.0), this is
now an end-to-end executable proof, not a content pin.

### skill-workflow.11 — Absent or empty ledger is silent at the gates
**REAL, at both gates, for every branch.** This is the scenario the prior
pass failed on. Now:
- **validate-feature**: `test_choices_row_branch_selection` runs the real
  fence for all four shapes — absent ledger (`○ Choices: no ledger`), a
  present-but-empty ledger (`✓ Choices: 0 needs-user`), a ledger with one
  open entry (`⚠ Choices: 1 needs-user entries...`), and — the case that was
  previously entirely missing — a ledger with entries where none are
  `needs-user` (also `✓ Choices: 0 needs-user`, proving `CHOICES_COUNT -eq 0`
  actually fires rather than being merely documented).
- **cleanup-feature**: `test_step_5_5_branch_selection` runs the real fence
  for all three shapes — absent ledger, an empty-entries ledger, and an
  open-entry ledger — asserting the exact distinct output per shape and that
  the wrong-case string does not leak into the right-case output
  (`forbidden not in out.stdout`).
- I independently confirmed via mutation testing (above) that these tests
  actually fail when the branches are swapped, closing the exact gap the
  prior FAIL identified.

### skill-workflow.12 — Standalone invocation against a commit range
**REAL for the driver half, nominal-by-design for the resolution-rule half —
unchanged from the prior pass and still a deliberate, documented scope
boundary, not a gap.** `test_end_to_end.py::TestStandaloneRangeInvocation`
drives `run_audit._cli()` with `change_id="range:<base>..<head>"` and
explicit `--base-sha`/`--head-sha`, asserting exit 0 and that the persisted
ledger records that `change_id` and `audited_range`. The remaining half —
that `/audit-choices` Step 1 resolves a bare `<base>..<head>` CLI argument
into that `range:` form — is an agent instruction with no programmatic entry
point; `tasks.md` (3.6, 3.7) and `design.md` both document this boundary
explicitly, and a driver-only test would be a bypass here, per the task's
own stated reasoning.

## Design Decisions Cross-Check (F1–F8)

Re-checked shipped behavior against `design.md` directly, not by trusting
the prior report:

- **F1** (hook placement): confirmed — `grep` on `iterate-on-implementation/SKILL.md`
  shows `### 11.5. Audit Choices (non-blocking)` at line 552 with the "NOT
  gated by `VENDOR_REVIEW`" first line at 554; `validate-feature`'s Choices
  row lives in Step 11 (line ~1042-1060) + Step 12 + After Validation;
  `cleanup-feature`'s Step 5.5 sits at line 553, immediately before Step 6
  at line 583, with Step 5a's early exit retargeted (`grep` confirms "skip
  to Step 5.5" replaces "skip to Step 6").
- **F2** (commit-on-entries-change, not bytes): confirmed in both prose and
  the shipped `entries`/`header.schema_version` comparison logic in Step
  11.5; `test_f2_comparison_behavior_unchanged_changed_new` still passes.
- **F3** (single shared reader, silent for both empty cases, never raises):
  confirmed — `needs_user.py` unchanged this round, tests still pass.
- **F4** (row, never a `## Choices` heading): confirmed by direct `grep` —
  no `^##* .*Choices` line exists in `validate-feature/SKILL.md`.
- **F5** (synthetic fixture id, archived artifacts as data): confirmed,
  `test_end_to_end.py` unchanged this round.
- **F6** (fails/unavailable taxonomy, partial-pair discard): confirmed via
  `grep` on `iterate-on-implementation/SKILL.md` — both `git checkout --`
  (tracked) and `rm -f` (untracked) discard paths present.
- **F7** (scenario ordinal table is authoritative): confirmed — `tasks.md`'s
  key table matches `specs/skill-workflow/spec.md`'s scenario order (read in
  full this round).
- **F8** (`--run-id` documented, "adds no writer and no behavior"):
  behavior unchanged and confirmed. **The wording nit flagged by the prior
  pass is now fixed.** `design.md`'s F8 text previously read "the one place
  the change touches `audit-choices` itself... adds no writer and no
  behavior," which was inconsistent with F3's new `needs_user.py` file
  (also under `skills/audit-choices/`). Commit `e649daae` corrects it to
  "Together with the F3 reader, this is the whole of what the change
  touches inside `audit-choices`: one new read-only script and one
  documented argument. Neither adds a writer..." — now consistent with
  `proposal.md`'s already-correct wording. Verified by reading the diff and
  the current file text directly.

## Scope

`git diff --stat main...HEAD` — same file set as the prior pass, plus this
round's fix: `design.md` (+7/-3, wording only) and
`skills/tests/audit-choices/test_workflow_hooks.py` (+117, the two new test
classes). No unrelated files touched.

## Result

**PASS.**

All four quality gates pass at the expected counts (133 audit-choices, 124
ci_coverage, both linters clean). `openspec validate --strict` passes. No
deployable surface, so Deploy/Smoke/Gen-Eval/E2E are correctly N/A. Every
task in `tasks.md` is checked off and maps to real shipped code. All five
`skill-workflow.8`–`.12` scenarios have real (executable, fixture-driven)
coverage of every branch that scenario turns on — including, now, scenario
11's gate-side distinguishability property, which is the specific thing the
prior pass found nominal. I independently reproduced the mutation test that
proves the new tests discriminate a real regression rather than being
executable-but-coincidentally-passing. All eight design decisions (F1–F8)
match shipped behavior, and the one cosmetic wording nit from the prior pass
(`design.md` F8) is now fixed and verified.

Pre-existing, out-of-scope conditions (repo-wide `make context-refresh`
pending-merge failures including `spec:skill-workflow`; `tests/roadmap-runtime`
and `tests/project-context-refresh` collection errors) were re-confirmed
unchanged and unrelated to this diff.
