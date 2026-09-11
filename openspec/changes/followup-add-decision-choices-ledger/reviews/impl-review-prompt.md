# Implementation Review — followup-add-decision-choices-ledger

You are an independent implementation reviewer. Review the code and
skill-instruction changes on branch `openspec/followup-add-decision-choices-ledger`
against `main`. This is an IMPLEMENTATION review: judge what was built, not the
plan that asked for it.

## Start here

```
git diff main...HEAD --stat
git diff main...HEAD -- skills/
```

The change wires an already-shipped, read-only decision auditor into three
lifecycle skills. Read the intent first, then the code:

- `openspec/changes/followup-add-decision-choices-ledger/design.md` — decisions
  F1 through F8. These are specific and were each written to correct a defect a
  review round found, so a "reasonable-looking variant" of one is usually a bug.
- `openspec/changes/followup-add-decision-choices-ledger/specs/skill-workflow/spec.md`
  — five WHEN/THEN scenarios the implementation must satisfy.
- `openspec/changes/followup-add-decision-choices-ledger/tasks.md` — per-task
  file scope and exact strings.

## What changed

- `skills/audit-choices/scripts/needs_user.py` — new read-only reader
- `skills/audit-choices/SKILL.md` — documents an optional `--run-id`
- `skills/iterate-on-implementation/SKILL.md` — new Step 11.5
- `skills/validate-feature/SKILL.md` — a `Choices:` row in the Step 11 report
  sketch and the Step 12 persisted-report heredoc, plus an After Validation echo
- `skills/cleanup-feature/SKILL.md` — new Step 5.5, and Step 5a's early exit
  retargeted from Step 6 to Step 5.5
- `skills/explore-feature/scripts/decision_index.py` + regenerated
  `docs/decisions/README.md`, `docs/guides/workflow.md`,
  `skills/install-manifest.json`
- `skills/tests/audit-choices/{test_needs_user,test_end_to_end,test_workflow_hooks}.py`

## What to look for

Report only defects you can justify by pointing at the code.

1. **Shell correctness in the Step 11.5 block.** It is a bash block that
   manipulates git. Trace every branch by hand, including the failure branches,
   and ask what each command actually does to each of the two ledger paths in
   each case: first audit with nothing committed, re-audit with an unchanged
   ledger, re-audit with changed entries, and a half-written pair in both the
   first-audit and re-audit cases. Check that a command intended for one path
   is not also applied to the other.
2. **Executability.** These SKILL.md blocks are read and executed by an agent.
   Flag anything written as literal shell that cannot run as shell, or anything
   whose intended executor (agent vs shell) is ambiguous at the point of use.
3. **Faithfulness to F2.** The commit-skip test must compare exactly `entries`
   and `header.schema_version`, and must commit when nothing is committed yet.
   A broader comparison never skips, because `header.git_sha` and
   `audited_range` move on every run.
4. **Read-only posture.** `needs_user.py` must open no file for writing and must
   never raise or exit non-zero. Check the error paths.
5. **Runtime-mirror resolution.** Both gate hooks must invoke the reader through
   `<skill-base-dir>/../audit-choices/scripts/needs_user.py`. A bare command or
   a repo-root `skills/...` path breaks under `.claude/skills/` and
   `.agents/skills/`.
6. **Scenario coverage.** For each of the five scenarios in the spec delta, find
   the assertion that pins it and say whether it actually would fail if the
   behavior regressed. Content assertions that match too loosely are findings.
7. **Test quality.** Do the tests in `skills/tests/audit-choices/` test behavior
   or restate the implementation? Would they catch the regressions they exist to
   catch?
8. **Scope.** The proposal says no change to the schema, ledger format, audit
   driver, `gate_logic.py`, or the read-only posture. Verify nothing outside the
   declared scope moved.

## Output format

Output ONLY valid JSON conforming to
`openspec/schemas/review-findings.schema.json`. No prose before or after. Each
finding requires `id` (integer), `type`, `criticality`, `axis`, `severity`,
`disposition`, and `description`; include `file_path` and `resolution`. Return
an empty findings array rather than inventing findings.
