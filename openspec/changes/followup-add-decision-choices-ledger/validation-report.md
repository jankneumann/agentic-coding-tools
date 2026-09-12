# Validation Report: followup-add-decision-choices-ledger

**Date**: 2026-09-11
**Commit**: a481fb89
**Branch**: openspec/followup-add-decision-choices-ledger--val1 (parent: openspec/followup-add-decision-choices-ledger)

## Change Shape

No deployable surface. `classify_deployable_surface(change_dir=..., changed_files=<62 files>)`
returns `DeployableSurface(deployable=False, source='derived', reason='all changed
paths are skills/docs/openspec (no deployable surface)')`. Deploy, Smoke, Gen-Eval
and E2E are therefore **N/A**, not skipped — confirmed by inspection of
`gate_logic.py`'s `ALWAYS_REQUIRED_PHASES`/`REQUIRED_PHASES` split. No containers
or podman socket were started for this validation.

## Phase Results

✓ Quality Gates: all four required gates pass, matching the expected counts
  - `cd skills && uv run pytest tests/audit-choices -q` → **126 passed**
  - `cd skills && bash install.sh --check` → "Skill install portability validation passed"
  - `cd skills && uv run python validate-feature/scripts/linters/dependency_direction.py --skills-root .` → "Dependency-direction validation passed"
  - `cd skills && uv run pytest tests/ci_coverage -q` → **124 passed**
- `skills/install-manifest.json` correctly declares the new `audit-choices` cross-skill dependency for `iterate-on-implementation`, `validate-feature`, and `cleanup-feature` (verified against the dependency-direction linter, which passes).

○ `make context-refresh` (pre-existing, out of scope): fails repo-wide with ~30
  unrelated active OpenSpec changes showing pending spec merges, including
  `spec:skill-workflow` — expected, since this change's delta merges into
  `openspec/specs/skill-workflow/spec.md` only at archive time. Confirmed this
  is not new: none of the failing validation_ids correspond to files this diff
  touches.

○ Test collection (pre-existing, out of scope): `tests/roadmap-runtime` and
  `tests/project-context-refresh` fail to collect (`ImportError: cannot import
  name 'LearningEntry'/'Checkpoint'/'Effort' from 'models'`). Confirmed none of
  the files in this diff touch `project-context-runtime/scripts/models.py`,
  `roadmap-runtime/`, or `project-context-refresh/`.

✓ Tasks: every task and checkpoint in `tasks.md` (3.0–3.7, both checkpoints) is
  checked `[x]`, and each maps to code that actually shipped:
  - 3.0 → `skills/audit-choices/scripts/needs_user.py` + `test_needs_user.py` (26 tests)
  - 3.1 → `iterate-on-implementation/SKILL.md` Step 11.5 (present, not-gated-by-VENDOR_REVIEW
    line present, self-contained work fence, F2 comparison on `entries`/`header.schema_version`,
    per-path tracked/untracked orphan discard, `Choices audit:` line in Step 12 summary)
  - 3.2 → `validate-feature/SKILL.md` Step 11 sketch + Step 12 heredoc both carry the
    `Choices:` row; After Validation echoes the `⚠` form; no `## Choices` heading
  - 3.3 → `cleanup-feature/SKILL.md` Step 5.5 inserted before Step 6; Step 5a's early
    exit retargeted from "skip to Step 6" to "skip to Step 5.5"
  - 3.4 → `docs/guides/workflow.md` command-ladder line and infrastructure-skill bullet
  - 3.5 → `decision_index.py::emit_readme` "Related: the choices ledger" paragraph,
    `docs/decisions/README.md` regenerated in the same commit (`make decisions` was run)
  - 3.6 → `test_end_to_end.py`, 12 tests, fixture seeded via `change_dir(...)` from the
    archived parent under a synthetic id (`fixture-decision-choices-ledger`)
  - 3.7 → `test_workflow_hooks.py`, the bulk of the audit-choices test suite

✓ Spec Compliance / Design Decisions F1–F8: see below — result is **FAIL**,
  not because behavior is wrong, but because one scenario's coverage is
  nominal rather than real.

## Spec Compliance — per-scenario assessment

The delta (`specs/skill-workflow/spec.md`) has five scenarios,
`skill-workflow.8`–`.12`. For each, I identified the assertion(s) that pin it
and asked whether that assertion would actually fail if the behavior
regressed.

### skill-workflow.8 — Workflow invocation is non-blocking
**REAL.** `TestIterateOnImplementationStep11_5` in `test_workflow_hooks.py`
extracts the *actual* Step 11.5 bash/python text (not restated prose) and
executes it against real git fixtures for every branch: the F2
entries/schema_version comparison (`test_f2_comparison_behavior_unchanged_changed_new`,
proving `header.git_sha` moving alone does NOT flip the verdict), the partial-pair
orphan discard for both the untracked-first-audit and tracked-truncated shapes
(`test_orphan_cleanup_behavior`), the dispatch-failed early-return path
(`test_dispatch_failed_branch_still_discards_orphan`), a failing `git commit`
leaving nothing staged (`test_commit_failure_leaves_no_staged_ledger`), a
failing `git checkout --` on the unchanged path
(`test_git_checkout_restore_failure_sets_skip_reason_not_silent`), and the
stale-half-via-`generated_at`-mismatch detection
(`test_stale_half_detected_via_generated_at_mismatch`). These are executable
proofs, not string matches — a regression in any of these code paths fails
the corresponding test. This is the most thoroughly covered scenario in the
change.

### skill-workflow.9 — needs-user entries surface at the validation gate
**REAL** for the entries-present case. `test_worktree_shaped_env_still_finds_the_ledger`
extracts the real Step 11 Choices-row snippet, runs it against a real git repo
with a genuine `choices.json` containing one `needs-user` entry, and asserts
the exact `⚠ Choices: 1 needs-user entries (choices.md)` output plus the
entry's `stable_id`. `test_no_ledger_path_survives_set_u` does the same for
the absent-ledger case under `set -u`. The underlying ordering/formatting
(`stable_id`, confidence, headline, least-confident-first) is proven
independently and behaviorally by `test_needs_user.py::TestMixedLedger`.

### skill-workflow.10 — needs-user entries surface at the cleanup gate
**PARTIALLY NOMINAL.** `TestCleanupFeatureStep5_5` only content-pins:
heading exists and mentions `needs_user.py`, "no new gate" wording present,
both empty-case strings present, Step 5a redirected to 5.5, and reader
invoked skill-relative. None of these executes the actual Step 5.5 bash block
(`CHOICES_JSON=...; if [ ! -f ... ]; then echo "no choices ledger"; else
CHOICES_LINES=$(...); if [ -n "$CHOICES_LINES" ]; then echo "$CHOICES_LINES";
else echo "no open choices"; fi; fi`) against a real fixture the way the
validate-feature counterpart does. The reader's own entry formatting is real
(shared with 3.0's tests), but nothing proves cleanup-feature's own three-way
branch actually selects the right output for a given ledger state — a
transposition bug (e.g. swapping the `if`/`else` bodies, or a quoting error
that makes `[ -n "$CHOICES_LINES" ]` always true/false) would pass every
existing assertion.

### skill-workflow.11 — Absent or empty ledger is silent at the gates
**REAL for the reader** (`test_needs_user.py`, and
`test_end_to_end.py::TestNeedsUserReaderIntegration`, which drives the reader
against both empty shapes from a real audited fixture). **Mixed for the two
gates' branch-selection**, which is exactly the property this scenario turns
on ("the two cases SHALL be distinguishable... MUST NOT render identically"):
- validate-feature: the absent-ledger branch (`○ Choices: no ledger`) is
  proven executably (`test_no_ledger_path_survives_set_u`). The
  ledger-present-but-zero-needs-user branch (`✓ Choices: 0 needs-user`,
  driven by `CHOICES_COUNT=$(printf '%s\n' "$CHOICES_LINES" | grep -c . ||
  true)`) is **not** executed by any test — only content-pinned
  (`test_no_ledger_and_zero_needs_user_forms_are_present_and_distinct` checks
  both strings appear in the file, not that the branch fires under the
  right condition).
- cleanup-feature: **neither** empty-case branch is executed by any test.
  `test_both_empty_case_wordings_present` only asserts both strings
  (`"no choices ledger"`, `"no open choices"`) appear somewhere inside the
  Step 5.5 section — a swap of which branch prints which string would still
  pass.

I manually traced both untested branches and they read correctly (`printf
'%s\n' "" | grep -c .` is `0`; the cleanup-feature if/else is a
straightforward absent-file / empty-string test), so I have no evidence of an
actual defect. But per the honesty requirement for this phase, an assertion
that would not fail on a real regression is nominal coverage regardless of
whether the underlying code happens to be correct today, and scenario 11 is
specifically the scenario whose entire content is "these two cases must not
render identically" — the one property most worth an executable proof.

### skill-workflow.12 — Standalone invocation against a commit range
**REAL for the driver half, nominal-by-design for the resolution-rule half —
and that split is explicit and correct, not a hidden gap.**
`test_end_to_end.py::TestStandaloneRangeInvocation` drives `run_audit._cli()`
with `change_id="range:<base>..<head>"` and explicit `--base-sha`/`--head-sha`,
asserting exit 0 and that the persisted ledger records that `change_id` and
`audited_range` — an executable proof of everything the driver itself does.
The remaining half of the scenario — that `/audit-choices` Step 1 actually
resolves a bare `<base>..<head>` CLI argument into that `range:` form — is an
agent instruction with no programmatic entry point, and `tasks.md` (3.6, 3.7)
and `design.md` both say so explicitly and explain why a driver-only test
would be a bypass here. `test_range_form_and_resolution_rule_documented`
correctly pins that instruction's wording as a content assertion, which is
the only mechanism available. This is a deliberate, documented, and
reasonable scope boundary, not the same thing as the untested branches under
scenario 11.

## Design Decisions Cross-Check (F1–F8)

Checked shipped behavior against `design.md`, not just against what looks
reasonable, per the four rounds of plan review and four rounds of
implementation review recorded in `plan-findings.md`, `reviews/round-{1..4}`,
and `reviews/impl-round-{1..4}`:

- **F1** (hook placement): confirmed — Step 11.5 sits between 11c and 12 with
  the required "NOT gated by VENDOR_REVIEW" first line; validate-feature's
  Choices row lives in Step 11 + Step 12 + After Validation; cleanup-feature's
  Step 5.5 sits immediately before Step 6, with Step 5a's early exit
  retargeted.
- **F2** (commit-on-entries-change, not bytes): confirmed both in prose and
  behaviorally (`test_f2_comparison_behavior_unchanged_changed_new` proves
  `header.git_sha` moving alone does not trigger a spurious commit).
- **F3** (single shared reader, silent for both empty cases, never raises):
  confirmed — `needs_user.py` never opens a file for writing
  (`TestOpensNoFileForWriting`), never raises even on malformed input
  (`TestMalformedButReadableLedger`, `TestCliIsTotal`), and is silent/`[]` for
  both empty shapes.
- **F4** (row, never a `## Choices` heading): confirmed —
  `test_no_choices_markdown_heading` asserts no `^#{1,6}\s+Choices\b` line
  exists in `validate-feature/SKILL.md`.
- **F5** (synthetic fixture id, archived artifacts as data): confirmed —
  `test_end_to_end.py` uses `change_dir(REAL_REPO_ROOT,
  "add-decision-choices-ledger")` to locate source artifacts but writes them
  under `fixture-decision-choices-ledger`, never the real archived id.
- **F6** (fails/unavailable taxonomy, partial-pair discard, one warn line):
  confirmed — two distinct `SKIP_REASON` strings for the two "unavailable"
  causes, tracked/untracked orphan discard via `git ls-files --error-unmatch`,
  and the stale-half detection via `generated_at` mismatch that the design
  text itself does not mention explicitly but which is a defensible
  strengthening of the same invariant (a fresh JSON next to a stale MD is a
  partial pair in spirit even though both files are individually non-empty).
- **F7** (scenario ordinal table is authoritative): confirmed — `tasks.md`'s
  key table matches the shipped `specs/skill-workflow/spec.md` scenario order.
- **F8** (`--run-id` documented, "the one place... adds no behavior"):
  behavior confirmed (`--run-id` documented, no new writer). One nit:
  round-4 plan review (codex finding 1) flagged `design.md`'s own F8 wording
  ("the one place the change touches `audit-choices` itself... adds no writer
  and no behavior") as inconsistent with F3's new `needs_user.py` file, which
  also lives under `skills/audit-choices/`. The fix landed in `proposal.md`
  ("that is the whole of what this change touches inside `audit-choices`: one
  new read-only script, one documented argument, no new writer") but
  `design.md`'s F8 text itself still carries the pre-fix phrasing verbatim.
  Cosmetic — the authoritative scope statement (`proposal.md`) is correct and
  the shipped code matches it — but noted since design.md is the reviewed
  artifact of record.

## Scope

`git diff --stat main...HEAD` touches only: `openspec/changes/followup-add-decision-choices-ledger/**`,
`skills/audit-choices/{SKILL.md,scripts/needs_user.py}`,
`skills/{cleanup-feature,validate-feature,iterate-on-implementation}/SKILL.md`,
`skills/explore-feature/scripts/decision_index.py`, `skills/install-manifest.json`,
`skills/tests/audit-choices/{test_end_to_end.py,test_needs_user.py,test_workflow_hooks.py}`,
and `docs/guides/workflow.md`/`docs/decisions/README.md`. No unrelated files.

## Result

**FAIL** — Behavior appears correct on inspection everywhere I checked, and
four rounds each of plan and implementation review already caught and fixed
real defects in exactly this area (the bash-fence slash-command bug, the
unguarded git commands, the `CHOICES_LINES` unbound-variable bug, the
`$OPENSPEC_PATH`/`$PROJECT_ROOT` worktree-resolution bug). But scenario 11's
branch-selection logic in `cleanup-feature/SKILL.md` Step 5.5 has **no
executable test at all** (only content-pin string presence), and
validate-feature's zero-needs-user branch has the same gap. Scenario 11 is
specifically the scenario whose entire content is "these two render forms
must not be identical" — the exact property an executable test, not a
string-presence test, is needed to prove. This is a real, fixable gap in test
depth, not a known behavioral defect.

**Recommended fix** (small, scoped): add to `test_workflow_hooks.py`, in the
style of `test_no_ledger_path_survives_set_u` /
`test_worktree_shaped_env_still_finds_the_ledger`:
1. One executable test that extracts the real cleanup-feature Step 5.5 bash
   block and runs it against three real fixtures — no `choices.json`, a
   `choices.json` with entries but none `needs-user`, and one with an open
   `needs-user` entry — asserting the exact three distinct outputs.
2. One executable test for validate-feature's `CHOICES_COUNT -eq 0` path
   (ledger present, zero `needs-user`) proving `✓ Choices: 0 needs-user` is
   what actually renders, mirroring the existing tests for the other two
   branches.

Address findings, then re-run `/validate-feature`.
