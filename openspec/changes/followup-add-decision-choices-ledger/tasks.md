# Tasks: followup-add-decision-choices-ledger

Carried forward from `add-decision-choices-ledger` Phase 3 on 2026-09-11 at
cleanup time. Numbering, dependencies, sizes and spec-scenario references are
preserved from the parent change so the dependency graph stays intact. Tasks
3.0 and 3.7 were added by plan iteration 1 (see `plan-findings.md`); 3.0 is
numbered below 3.1 because 3.2 and 3.3 depend on it.

Dependencies on parent task `2.8` (create `skills/audit-choices/SKILL.md`) are
satisfied: that task is complete and archived.

## Scenario key

`skill-workflow.N` ordinals are the parent's numbering, kept so this graph
reads the same as the archived one. 1–6 are canonical in
`openspec/specs/skill-workflow/spec.md` (merged from the parent); 7–11 are in
this change's `specs/skill-workflow/spec.md`.

| Ordinal | Scenario | Location |
|---------|----------|----------|
| skill-workflow.1 | Ledger pair is schema-valid | canonical |
| skill-workflow.2 | Auditor writes only the ledger pair | canonical |
| skill-workflow.3 | Unreported decision is flagged | canonical |
| skill-workflow.4 | Re-audit is idempotent | canonical |
| skill-workflow.5 | Rendering enforces the ranking invariant | canonical |
| skill-workflow.6 | Adverse verdicts never block | canonical |
| skill-workflow.7 | Workflow invocation is non-blocking | this delta |
| skill-workflow.8 | needs-user entries surface at the validation gate | this delta |
| skill-workflow.9 | needs-user entries surface at the cleanup gate | this delta |
| skill-workflow.10 | Absent or empty ledger is silent at the gates | this delta |
| skill-workflow.11 | Standalone invocation against a commit range | this delta |

Design decisions `D<n>` refer to the archived parent's `design.md`; `F<n>`
refer to this change's `design.md`.

## Phase 3 — Workflow hooks and documentation

- [ ] 3.0 Add the read-only `needs_user.py` reader to audit-choices
  **Spec scenarios**: skill-workflow.8, skill-workflow.9, skill-workflow.10
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
  **Spec scenarios**: skill-workflow.7 (Workflow invocation is non-blocking)
  **Design decisions**: D6, F1, F2, F6
  **Dependencies**: none (parent 2.8 archived)
  **Files**: `skills/iterate-on-implementation/SKILL.md`
  **Size**: S
  Insert `### 11.5. Audit Choices (non-blocking)` between 11c and 12: invoke
  `/audit-choices $CHANGE_ID` (its Steps 1–5 own range resolution and the
  independent sub-agent dispatch) with
  `run_id=iterate-on-implementation-<UTC ISO timestamp>`; on success stage and
  commit the ledger pair as `chore(choices): audit ledger for <change-id>`
  only when it changed; wrap the whole step in a warn-and-continue guard that
  prints one `audit-choices: skipped (<reason>) — continuing to summary` line
  for every failure/unavailable branch enumerated in F6; add a `Choices
  audit:` line to the Step 12 summary template.
- [ ] 3.2 Surface needs-user ledger entries at the validate-feature gate
  **Spec scenarios**: skill-workflow.8 (needs-user entries surface at the validation gate), skill-workflow.10
  **Design decisions**: D6, F1, F4
  **Dependencies**: 3.0
  **Files**: `skills/validate-feature/SKILL.md`
  **Size**: S
  Add a `Choices:` row to the Step 11 Phase Results template (`○` no ledger,
  `✓` ledger with zero needs-user, `⚠ Choices: <n> needs-user entries
  (choices.md)` followed by `needs_user.py` output lines), echo the `⚠` form
  once under After Validation, and state explicitly that the row never
  changes Result. Never emit a `## Choices` section (F4: `gate_logic.py`
  parses `##` sections).
- [ ] 3.3 Surface needs-user ledger entries at the cleanup-feature gate
  **Spec scenarios**: skill-workflow.9 (needs-user entries surface at the cleanup gate), skill-workflow.10
  **Design decisions**: D6, F1
  **Dependencies**: 3.0
  **Files**: `skills/cleanup-feature/SKILL.md`
  **Size**: S
  Insert `### 5.5. Surface open needs-user choices` immediately before the
  `### 6. Archive OpenSpec Proposal` heading (cleanup-feature has two `5c`
  headings and a `5d` between the open-task migration and archive; anchor on
  Step 6, not on 5c): run `needs_user.py --change-id "$CHANGE_ID"`, print the lines (or
  "no open choices"), and proceed to archive on the existing confirmation —
  no prompt, no migration, no new gate. Note in the step that the ledger
  archives with the change directory unchanged.
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
- [ ] 3.6 Run an end-to-end audit against an archived-change fixture
  **Spec scenarios**: skill-workflow.1 through skill-workflow.6 (driver run), skill-workflow.7 (forced failure), skill-workflow.8 through skill-workflow.10 (reader output), skill-workflow.11 (range form)
  **Design decisions**: F5, F6
  **Dependencies**: 3.0, 3.1, 3.2, 3.3
  **Files**: `skills/tests/audit-choices/test_end_to_end.py`
  **Size**: M
  pytest, not a manual run. Build a `tmp_path` git repo (pattern of
  `test_readonly_posture.fixture_repo`) whose `openspec/changes/<id>/` holds
  the archived parent's `proposal.md`, `design.md` and `session-log.md`
  copied from `openspec/changes/archive/2026-09-10-add-decision-choices-ledger/`
  (resolve the archive dir at test time — never pin the path); one base and
  one implementing commit; a canned candidate set with one `sound`, one
  `unsound`, one `needs-user`, one matching a session-log Decision bullet.
  Assert: schema-valid pair with six-field header (1); working-tree snapshot
  diff is exactly the pair (2); `self_reported` resolves both ways (3);
  second run keeps every `stable_id` and the count (4); `choices.md` order
  (5); `ok=True` with adverse verdicts (6); an unreadable repo root gives
  `ok=False` and CLI exit 0 (7); `needs_user.py` lists exactly the
  `needs-user` entry, is empty for a no-ledger change (8–10); the range form
  records `change_id == "range:<base>..<head>"` and exits 0 (11).
- [ ] 3.7 Pin the three workflow hooks with SKILL.md content tests
  **Spec scenarios**: skill-workflow.7, skill-workflow.8, skill-workflow.9
  **Design decisions**: F1, F2, F4
  **Dependencies**: 3.1, 3.2, 3.3
  **Files**: `skills/tests/audit-choices/test_workflow_hooks.py`
  **Size**: S
  In the style of `skills/tests/cleanup-feature/test_skill_md.py`: assert
  iterate-on-implementation has a `### 11.5.` heading containing
  `audit-choices`, the skip line, and the `chore(choices)` commit; assert
  validate-feature's Step 11 template has a `Choices:` row and no line in
  the file begins with `## Choices` (inline-code mentions of the literal are
  fine; a heading is not); assert cleanup-feature has `### 5.5.`
  calling `needs_user.py` and states no new gate.
- [ ] Checkpoint: run the four skill gates (`cd skills && bash install.sh --check`; `python validate-feature/scripts/linters/dependency_direction.py --skills-root .`; `make context-refresh PYTHON=skills/.venv/bin/python`; `python -m pytest tests/ci_coverage -q`), resync runtime copies (`bash skills/install.sh --mode rsync --deps none --python-tools none`), review diff, verify scope
