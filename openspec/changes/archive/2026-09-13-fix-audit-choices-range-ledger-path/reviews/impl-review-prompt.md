# Implementation Review — fix-audit-choices-range-ledger-path

You are an independent implementation reviewer. Review the code on branch
`openspec/fix-audit-choices-range-ledger-path` against `main`. This is an
IMPLEMENTATION review: judge what was built, not the plan that asked for it.

## Start here

```
git diff main...HEAD --stat
git diff main...HEAD -- skills/
```

Read the intent first, then the code:

- `openspec/changes/fix-audit-choices-range-ledger-path/design.md` — decisions
  D1 through D8. Three rounds of plan review shaped these; several are
  corrections of defects reviewers found, so a reasonable-looking variant is
  usually a reintroduced bug.
- `openspec/changes/fix-audit-choices-range-ledger-path/specs/skill-workflow/spec.md`
  — two MODIFIED requirements, scenarios 12 through 15.
- `openspec/changes/fix-audit-choices-range-ledger-path/tasks.md` — per-task
  file scope and exact assertions.

## What changed

The standalone `<base>..<head>` audit form wrote its ledger to
`openspec/changes/range:abc..def/` — a directory that is not a change, inside
the tree every sweep over `openspec/changes/` reads. It now routes to
`openspec/choices/<run-id>/` with `latest.*` pointers and retention.

- `skills/shared/artifact_paths.py` — new; run-id format and retention,
  extracted from `prioritize-proposals`
- `skills/audit-choices/scripts/choices_paths.py` — new; destination routing
- `skills/audit-choices/scripts/run_audit.py`, `SKILL.md`
- `skills/prioritize-proposals/scripts/{priorities_paths.py,retention.py}` —
  migrated onto the shared helper, output must be unchanged
- `docs/guides/workflow.md` and five test modules

## What to look for

Report only defects you can justify by pointing at code.

1. **D8's collision guard.** Two audits in the same UTC second at the same
   `HEAD` must not share a directory. Check the suffix logic, that it tests the
   archive as well as the active path, and that `RUN_ID_RE` accepts the
   suffixed name — an unextended regex makes `list_active_runs` skip exactly
   the directories the guard creates, so retention silently stops bounding the
   tree while the bounding test still passes. Trace it by hand.
2. **D4's characterization guard.** `test_priorities_paths.py`,
   `test_retention.py`, `test_smoke_e2e.py` and `prioritize-proposals/SKILL.md`
   must be byte-unchanged from `main`, and
   `test_output_characterization.py` must prove the migration changed nothing
   observable. Verify both, and say what breakage could still pass it.
3. **D6's closed write set.** A range run may touch only the run directory's
   pair, `latest.*`, and retention's archive move. Can a run produce a fourth
   effect? Is the read-only posture test actually closed, given a retention
   move deletes files from their original paths?
4. **D3.** No definition of a moved name may survive in
   `skills/prioritize-proposals/scripts/` — only re-exports. Grep and confirm.
5. **Scenario coverage.** For each of scenarios 12 through 15, find the
   assertion that pins it and say whether it would fail if the behavior
   regressed. Content assertions that match too loosely are findings.
6. **Scope.** The proposal claims no change to the schema, ledger format, entry
   pipeline, six-field header, or exit-code contract. Verify.
7. **Test quality.** Do the tests test behavior or restate the implementation?

## Output format

Output ONLY valid JSON conforming to
`openspec/schemas/review-findings.schema.json`. No prose before or after. Each
finding requires `id` (integer), `type`, `criticality`, `axis`, `severity`,
`disposition`, and `description`; include `file_path` and `resolution`. Return
an empty findings array rather than inventing findings.
