# Tasks: followup-add-decision-choices-ledger

Carried forward from `add-decision-choices-ledger` Phase 3 on 2026-09-11 at
cleanup time. The task numbering, dependencies and sizes are the parent's.
Tasks 3.0 and 3.7 were added by plan iteration 1 (see `plan-findings.md`);
3.0 is numbered below 3.1 because 3.2 and 3.3 depend on it. Scenario ordinals
were corrected in plan review round 1 (see F7 and `reviews/round-1/`).

Dependencies on parent task `2.8` (create `skills/audit-choices/SKILL.md`) are
satisfied: that task is complete and archived.

## Scenario key

`skill-workflow.N` ordinals follow the **archived parent delta's document
order** for 1–7 and this change's delta for 8–12. All seven parent scenarios
merged into `openspec/specs/skill-workflow/spec.md`; none is a delta-only
scenario. Do not renumber without updating this table.

| Ordinal | Scenario | Location |
|---------|----------|----------|
| skill-workflow.1 | Ledger pair is schema-valid | canonical |
| skill-workflow.2 | Missing ledger does not block archive | canonical |
| skill-workflow.3 | Auditor writes only the ledger pair | canonical |
| skill-workflow.4 | Adverse verdicts never block | canonical |
| skill-workflow.5 | Unreported decision is flagged | canonical |
| skill-workflow.6 | Re-audit is idempotent | canonical |
| skill-workflow.7 | Rendering enforces the ranking invariant | canonical |
| skill-workflow.8 | Workflow invocation is non-blocking | this delta |
| skill-workflow.9 | needs-user entries surface at the validation gate | this delta |
| skill-workflow.10 | needs-user entries surface at the cleanup gate | this delta |
| skill-workflow.11 | Absent or empty ledger is silent at the gates | this delta |
| skill-workflow.12 | Standalone invocation against a commit range | this delta |

Design decisions `D<n>` refer to the archived parent's `design.md`; `F<n>`
refer to this change's `design.md`.

## Phase 3 — Workflow hooks and documentation

- [ ] 3.0 Add the read-only `needs_user.py` reader to audit-choices
  **Spec scenarios**: skill-workflow.9, skill-workflow.10, skill-workflow.11
  **Design decisions**: F3
  **Dependencies**: none (parent 2.8 archived)
  **Files**: `skills/audit-choices/scripts/needs_user.py`, `skills/tests/audit-choices/test_needs_user.py`
  **Size**: S
  Write the test first: absent ledger → empty stdout, exit 0; ledger with
  zero `needs-user` → empty stdout, exit 0; mixed ledger → only `needs-user`
  lines, least-confident first, `stable_id`/confidence/headline per line;
  `--format json` → the same entries as a JSON array; unreadable JSON → exit 0
  with one stderr warning. Reuse `choices_ledger.rank_entries`; open no file
  for writing.

- [ ] 3.1 Add the Step 11.5 audit invocation to iterate-on-implementation
  **Spec scenarios**: skill-workflow.8 (Workflow invocation is non-blocking)
  **Design decisions**: D6, F1, F2, F6, F8
  **Dependencies**: none (parent 2.8 archived)
  **Files**: `skills/iterate-on-implementation/SKILL.md`, `skills/audit-choices/SKILL.md`
  **Size**: S
  In `iterate-on-implementation/SKILL.md`, insert `### 11.5. Audit Choices
  (non-blocking)` between 11c and 12. Its **first line** must state that the
  step is not gated by `VENDOR_REVIEW` and runs on every converged iteration
  including runs that skipped Step 11 (F1 — Step 11 opens with "Skip this step
  if `VENDOR_REVIEW=false`", and an `11.x` heading otherwise reads as part of
  that skipped block). The step invokes `/audit-choices $CHANGE_ID --run-id
  iterate-on-implementation-<UTC ISO timestamp>`; `/audit-choices` Steps 1–5
  own range resolution and the independent sub-agent dispatch.
  Then, per F2: verify **both** `choices.json` and `choices.md` exist and are
  non-empty (if only one does, restore both with `git checkout --` and take
  the skip line — F6); compare the entry payload (`choices.json` with
  `generated_at` and `run_id` removed from the header) against the committed
  revision; when only the volatile header moved, restore the pair and commit
  nothing; otherwise stage **both paths under the change directory** —
  `git add "openspec/changes/$CHANGE_ID/choices.json"
  "openspec/changes/$CHANGE_ID/choices.md"`, not a bare `choices.md` — and
  commit `chore(choices): audit ledger for <change-id>`.
  Wrap the whole step in a warn-and-continue guard printing exactly one
  `audit-choices: skipped (<reason>) — continuing to summary` line for every
  branch enumerated in F6, and add a `Choices audit:` line to the Step 12
  summary template.
  In `audit-choices/SKILL.md`, add the optional trailing `--run-id <id>` to
  the Arguments section (F8): documentation only, `run_audit.py` has required
  `--run-id` since Phase 2. Add no writer and no behavior — the read-only
  contract and `test_readonly_posture.py` stay as they are.

- [ ] 3.2 Surface needs-user ledger entries at the validate-feature gate
  **Spec scenarios**: skill-workflow.9, skill-workflow.11
  **Design decisions**: D6, F1, F4
  **Dependencies**: 3.0
  **Files**: `skills/validate-feature/SKILL.md`
  **Size**: S
  Step 11 of this skill contains **two** Phase Results blocks and the row must
  reach both: the illustrative `### Phase Results` sketch that documents the
  report format, and the Step 10 phase-results assembly whose output fills the
  `<phase results from Step 10>` placeholder in the heredoc that actually
  writes `$REPORT_FILE` under an `## Phase Results` heading. Editing only the
  sketch produces a documented row that never appears in
  `validation-report.md`.
  Row forms: `○ Choices: no ledger`, `✓ Choices: <n> entries, 0 needs-user`,
  or `⚠ Choices: <n> needs-user entries (choices.md)` followed by
  `needs_user.py` output lines. Echo the `⚠` form once under After Validation.
  State explicitly that the row never changes Result (`⚠` is already "passed
  with warnings"). Never emit a `## Choices` section — `gate_logic.py` reads a
  fixed allow-list of phase headings and the row form leaves nothing for a
  future allow-list edit to pick up (F4).

- [ ] 3.3 Surface needs-user ledger entries at the cleanup-feature gate
  **Spec scenarios**: skill-workflow.10, skill-workflow.11
  **Design decisions**: D6, F1
  **Dependencies**: 3.0
  **Files**: `skills/cleanup-feature/SKILL.md`
  **Size**: S
  Two edits in one file. First, insert `### 5.5. Surface open needs-user
  choices` immediately before the `### 6. Archive OpenSpec Proposal` heading
  (the file labels two different headings `5c` and has a `5d` between the
  open-task migration and archive; anchor on Step 6, never on 5c). It runs
  `needs_user.py --change-id "$CHANGE_ID"`, prints the lines or `no open
  choices`, and proceeds to archive on the existing confirmation — no prompt,
  no migration, no new gate. Note that the ledger archives with the change
  directory unchanged.
  Second, retarget the Step 5a early exit: `#### 5a. Detect open tasks` ends
  with "If **all tasks are checked** (`- [x]`), skip to Step 6", which is the
  common happy path and jumps straight over 5.5. Point it at Step 5.5 instead
  so a fully-completed change still surfaces its open choices before archive.

- [ ] Checkpoint: run `cd skills && uv run pytest tests/audit-choices -q`, `bash skills/install.sh --check`, review diff, verify scope

- [ ] 3.4 Update docs/guides/workflow.md with the audit-choices skill
  **Dependencies**: none (parent 2.8 archived)
  **Files**: `docs/guides/workflow.md`
  **Size**: XS
  Add `/audit-choices <change-id> | <base>..<head>` under the
  `/iterate-on-implementation` line in the command ladder (annotated as
  automatic at Step 11.5, standalone on demand) and one bullet under
  Infrastructure Skills naming the ledger pair and the two gates that surface
  it.

- [ ] 3.5 Add the ledger positioning note at the decision-index README producer
  **Design decisions**: D5
  **Dependencies**: none (parent 2.8 archived)
  **Files**: `skills/explore-feature/scripts/decision_index.py`, `docs/decisions/README.md` (regenerated, not hand-edited)
  **Size**: S
  In `emit_readme`, add a short "Related: the choices ledger" paragraph after
  "What belongs in this index": `choices.json`/`choices.md` are the
  independently audited, per-change complement; they cross-reference this
  index via `<change-id>#D<n>` and never write to it. Then run
  `make decisions` and stage `docs/decisions/` in the same commit so the CI
  freshness gate stays green.

- [ ] 3.6 Pin the driver end-to-end against archived-change fixture data
  **Spec scenarios**: skill-workflow.1 through skill-workflow.7 (driver run), skill-workflow.9 through skill-workflow.11 (reader output), skill-workflow.12 (range form)
  **Design decisions**: F5, F6
  **Dependencies**: 3.0
  **Files**: `skills/tests/audit-choices/test_end_to_end.py`
  **Size**: M
  pytest, not a manual run. Scenario 8 is **not** covered here — it is
  `iterate-on-implementation` behavior and belongs to 3.1 + 3.7 — so this task
  does not depend on 3.1–3.3.
  Build a `tmp_path` git repo (pattern of
  `test_readonly_posture.fixture_repo`) whose `openspec/changes/<id>/` holds
  the archived parent's `proposal.md`, `design.md` and `session-log.md`,
  copied as fixture data. Locate them with `change_dir()` from
  `skills/tests/_shared/openspec_paths.py` passing change id
  `add-decision-choices-ledger` — that helper returns the active directory
  when present and the archived one otherwise, and a guard test enforces its
  use over a literal path. Make one base and one implementing commit, and a
  canned candidate set with one `sound`, one `unsound`, one `needs-user`, and
  one matching a session-log Decision bullet.
  Assert: schema-valid pair with the six-field header (1); absence does not
  block (2); the working-tree snapshot diff is exactly the pair (3); `ok=True`
  with adverse verdicts present (4); `self_reported` resolves both ways (5);
  a second run keeps every `stable_id` and the count (6); `choices.md` order
  (7); `needs_user.py` lists exactly the `needs-user` entry and is empty for
  a change with no ledger (9–11). For (12), invoke the CLI with a single
  `<base>..<head>` **argument** and assert the audited base and head were
  derived from it — a test that hands the driver a precomputed
  `range:<base>..<head>` change id passes even when argument parsing is
  broken.

- [ ] 3.7 Pin the three workflow hooks with SKILL.md content tests
  **Spec scenarios**: skill-workflow.8, skill-workflow.9, skill-workflow.10, skill-workflow.11
  **Design decisions**: F1, F2, F4, F6
  **Dependencies**: 3.1, 3.2, 3.3
  **Files**: `skills/tests/audit-choices/test_workflow_hooks.py`
  **Size**: S
  In the style of `skills/tests/cleanup-feature/test_skill_md.py`:
  - iterate-on-implementation has a `### 11.5.` heading containing
    `audit-choices`, wording stating the step is not gated by
    `VENDOR_REVIEW`, the single skip line, the both-files-present check, and
    a `git add` whose two pathspecs are both under
    `openspec/changes/$CHANGE_ID/` (assert no bare `choices.md` argument).
  - validate-feature's Step 10 phase-results assembly and its Step 11 sketch
    both carry a `Choices:` row, no line in the file begins with
    `## Choices` (inline-code mentions are fine, a heading is not), and the
    `○` no-ledger and `✓` zero-needs-user forms are both present
    (scenario 11's gate side).
  - cleanup-feature has a `### 5.5.` calling `needs_user.py`, states no new
    gate, carries the `no open choices` wording, and its Step 5a early exit
    names Step 5.5 rather than Step 6.
  - audit-choices Arguments documents `--run-id`.

- [ ] Checkpoint: run the four skill gates (`cd skills && bash install.sh --check`; `python validate-feature/scripts/linters/dependency_direction.py --skills-root .`; `make context-refresh PYTHON=skills/.venv/bin/python`; `python -m pytest tests/ci_coverage -q`), resync runtime copies (`bash skills/install.sh --mode rsync --deps none --python-tools none`), review diff, verify scope
