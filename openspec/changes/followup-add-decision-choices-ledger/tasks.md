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

- [x] 3.0 Add the read-only `needs_user.py` reader to audit-choices
  **Spec scenarios**: skill-workflow.9, skill-workflow.10, skill-workflow.11
  **Design decisions**: F3
  **Dependencies**: none (parent 2.8 archived)
  **Files**: `skills/audit-choices/scripts/needs_user.py`, `skills/tests/audit-choices/test_needs_user.py`
  **Size**: S
  Write the test first, and spell the empty cases per format. Text mode:
  absent ledger → empty stdout, exit 0; ledger with zero `needs-user` →
  empty stdout, exit 0; mixed ledger → only `needs-user` lines,
  least-confident first, `stable_id`/confidence/headline per line. JSON mode
  (`--format json`): the same entries as a JSON array, and `[]` — not empty
  stdout — for both empty cases, so a caller can pipe it without branching.
  Either mode: unreadable JSON → exit 0 with one stderr warning (and `[]` in
  json mode). Reuse `choices_ledger.rank_entries`; open no file
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
  the skip line, discarding the orphan with `git checkout --` when the path
  is tracked and `rm -f` when it is not, since `git checkout --` does nothing
  for an untracked first-run file — F6); parse the fresh `choices.json` and
  the committed revision
  (`git show HEAD:openspec/changes/$CHANGE_ID/choices.json`) and compare
  exactly `entries` and `header.schema_version` — the six header fields are
  nested under `header`, there is no root-level `schema_version` — ignoring
  `header.generated_at`, `header.run_id`, `header.git_sha`,
  `header.generator`, `header.event_kind`, and root-level `change_id`,
  `audited_range` and `auditor`, all of which move on every run (F2); when
  there is no committed revision the pair is new and always commits; when
  both match, restore the pair (`git checkout --`) and commit nothing;
  otherwise stage **both paths under the change directory** —
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
  The row must reach **two** places, in two different steps. `### 11.
  Validation Report` holds an illustrative report sketch with an
  `### Phase Results` heading — that documents the format. `### 12. Persist
  Report` holds the `cat > "$REPORT_FILE"` heredoc that actually writes the
  file, under an `## Phase Results` heading whose entire body is the
  placeholder `<phase results from Step 10>`. (Step 10 is Teardown; that
  placeholder is a stale cross-reference already in the skill — do not
  propagate it, and do not attempt to fix it here.) Editing only the Step 11
  sketch produces a documented row that never reaches
  `validation-report.md`, so Step 12 needs explicit instruction to carry the
  `Choices:` row into the persisted report.
  Row forms: `○ Choices: no ledger`, `✓ Choices: 0 needs-user`,
  or `⚠ Choices: <n> needs-user entries (choices.md)` followed by the reader's
  output lines. The row picks between `○` and `✓` by testing for
  `openspec/changes/$CHANGE_ID/choices.json` itself — the reader is silent for
  both empty cases by design (F3) and scenario 11 requires them to render
  differently. Invoke the reader the way this repo invokes every sibling-skill
  script, `python3 "<skill-base-dir>/../audit-choices/scripts/needs_user.py"`,
  never a bare command or a repo-root `skills/...` path: the runtime mirrors
  under `.claude/skills/` and `.agents/skills/` have neither on the path. Echo the `⚠` form once under After Validation.
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
  `python3 "<skill-base-dir>/../audit-choices/scripts/needs_user.py"
  --change-id "$CHANGE_ID"` — skill-relative, like every other sibling-skill
  call in this repo, so it resolves inside the `.claude/skills/` and
  `.agents/skills/` mirrors too. It prints the entry lines when there are
  any; otherwise it distinguishes the two empty cases scenario 11 requires to
  differ, by testing for `openspec/changes/$CHANGE_ID/choices.json` and
  printing `no choices ledger` when it is absent and `no open choices` when
  it exists with nothing open. Then it proceeds to archive on the existing
  confirmation — no prompt, no migration, no new gate. Note that the ledger archives with the change
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
  **Spec scenarios**: skill-workflow.1, skill-workflow.3 through skill-workflow.7 (driver run), skill-workflow.11 (reader half only)
  **Design decisions**: F5, F6
  **Dependencies**: 3.0
  **Files**: `skills/tests/audit-choices/test_end_to_end.py`
  **Size**: M
  pytest, not a manual run. Scenario 8 is **not** covered here — it is
  `iterate-on-implementation` behavior and belongs to 3.1 + 3.7 — so this task
  does not depend on 3.1–3.3.
  Build a `tmp_path` git repo (pattern of
  `test_readonly_posture.fixture_repo`). Read the archived parent's
  `proposal.md`, `design.md` and `session-log.md` from the real repo with
  `change_dir(real_repo_root, "add-decision-choices-ledger")` from
  `skills/tests/_shared/openspec_paths.py` — that helper returns the active
  directory when present and the archived one otherwise, and a guard test
  enforces its use over a literal path. Copy them into the fixture repo under
  a **synthetic** change id (`fixture-decision-choices-ledger`), not the real
  one: the real id is how you find the source artifacts, never how the
  fixture names its own active change, or the test re-encodes the archival
  coupling the path-stability rule exists to prevent. Make one base and one implementing commit, and a
  canned candidate set with one `sound`, one `unsound`, one `needs-user`, and
  one matching a session-log Decision bullet.
  Assert: schema-valid pair with the six-field header (1); the working-tree
  snapshot diff is exactly the pair (3); `ok=True` with adverse verdicts
  present (4); `self_reported` resolves both ways (5); a second run keeps
  every `stable_id` and the count (6); `choices.md` order (7);
  `needs_user.py` lists exactly the `needs-user` entry, is empty for a change
  with no ledger, and prints `[]` in json mode for both empty cases — the
  reader half of (11).
  Also drive the driver with `change_id=f"range:{base}..{head}"` and explicit
  `--base-sha`/`--head-sha`, asserting exit 0 and that the persisted ledger
  records that `change_id` and audited range. This is the executable half of
  scenario 12 and nothing more: it does **not** show that a `<base>..<head>`
  argument resolves, which is why 3.7 pins the resolution rule separately.
  **Not covered here, deliberately.** skill-workflow.2 ("Missing ledger does
  not block archive") is validation and archive behavior, which a driver
  fixture never exercises; it stays with the parent's own coverage.
  skill-workflow.8 is `iterate-on-implementation` behavior and belongs to 3.1
  + 3.7. skill-workflow.12 has no programmatic entry point to call:
  `run_audit.py` takes `--change-id`, `--base-sha` and `--head-sha`
  separately, and the `<base>..<head>` argument form is resolved by
  `audit-choices/SKILL.md` Step 1 as an agent instruction. Under the
  proposal's no-driver-change constraint it is pinned by 3.7 as a content
  assertion instead — a pytest that fabricates `change_id="range:..."` would
  pass whether or not the documented resolution works, which is exactly the
  bypass this task forbids elsewhere.

- [ ] 3.7 Pin the three workflow hooks with SKILL.md content tests
  **Spec scenarios**: skill-workflow.8, skill-workflow.9, skill-workflow.10, skill-workflow.11, skill-workflow.12
  **Design decisions**: F1, F2, F4, F6, F8
  **Dependencies**: 3.1, 3.2, 3.3
  **Files**: `skills/tests/audit-choices/test_workflow_hooks.py`
  **Size**: S
  In the style of `skills/tests/cleanup-feature/test_skill_md.py`:
  - iterate-on-implementation has a `### 11.5.` heading containing
    `audit-choices`, wording stating the step is not gated by
    `VENDOR_REVIEW`, the single skip line, the both-files-present check, and
    a `git add` whose two pathspecs are both under
    `openspec/changes/$CHANGE_ID/` (assert no bare `choices.md` argument).
  - the same step states the F2 commit rule: that the comparison is on the
    `entries` array against the committed revision, and that a run whose
    entries are unchanged restores the pair and commits nothing. Without this
    assertion a rewrite could drop the comparison and emit a content-free
    `chore(choices):` commit on every run while still passing every other
    check here.
  - validate-feature carries a `Choices:` row in **both** the Step 11 report
    sketch and the Step 12 `$REPORT_FILE` heredoc, no line in the file begins
    with `## Choices` (inline-code mentions are fine, a heading is not), and
    the `○` no-ledger and `✓` zero-needs-user forms are both present and
    distinct (scenario 11's gate side), and the After Validation section
    mentions the `⚠` Choices echo — F1 names that prompt as half the human
    decision point, and without this assertion a rewrite could drop the echo
    and still pass every other check here.
  - cleanup-feature has a `### 5.5.` calling `needs_user.py`, states no new
    gate, carries **both** empty-case wordings (`no choices ledger` and `no
    open choices`) so scenario 11's two cases stay distinguishable, and its
    Step 5a early exit names Step 5.5 rather than Step 6.
  - both gate hooks invoke the reader through
    `<skill-base-dir>/../audit-choices/scripts/needs_user.py`; assert no bare
    `needs_user.py` command and no repo-root `skills/audit-choices/...` path
    appears in either file's hook block.
  - the Step 11.5 orphan cleanup names both the tracked case
    (`git checkout --`) and the untracked first-audit case (`rm -f`).
  - audit-choices Arguments documents `--run-id`, and documents the
    `<base-sha>..<head-sha>` form together with the Step 1 rule that an
    explicit range argument is used as given rather than resolved from a
    change's base commit (scenario 12 — see 3.6 for why this is a content
    assertion and not a driver test).

- [ ] Checkpoint: run the four skill gates (`cd skills && bash install.sh --check`; `python validate-feature/scripts/linters/dependency_direction.py --skills-root .`; `make context-refresh PYTHON=skills/.venv/bin/python`; `python -m pytest tests/ci_coverage -q`), resync runtime copies (`bash skills/install.sh --mode rsync --deps none --python-tools none`), review diff, verify scope
