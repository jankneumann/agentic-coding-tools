# Plan Review — fix-audit-choices-range-ledger-path

You are an independent plan reviewer. Review the OpenSpec proposal for change
`fix-audit-choices-range-ledger-path`. This is a PLAN review: judge the plan,
not an implementation (none exists yet).

## Read these (paths relative to the repository root)

- `openspec/changes/fix-audit-choices-range-ledger-path/proposal.md`
- `openspec/changes/fix-audit-choices-range-ledger-path/design.md` — decisions D1–D8
- `openspec/changes/fix-audit-choices-range-ledger-path/tasks.md`
- `openspec/changes/fix-audit-choices-range-ledger-path/specs/skill-workflow/spec.md`
- `openspec/changes/fix-audit-choices-range-ledger-path/work-packages.yaml`
- `openspec/changes/fix-audit-choices-range-ledger-path/plan-findings.md` (prior self-review; do not merely repeat it)

## The problem being fixed

`skills/audit-choices/scripts/run_audit.py` derives its output directory from
the raw `change_id`. In the standalone `<base-sha>..<head-sha>` form that id is
the literal string `range:<base>..<head>`, so the ledger pair lands in
`openspec/changes/range:abc1234..def5678/` — a directory that is not a change,
inside the tree every sweep over `openspec/changes/` reads.

## Context you need

- `skills/prioritize-proposals/` is the precedent: same six-field artifact
  header, same problem, resolved by moving to `openspec/priorities/<run-id>/`.
  Its `priorities_paths.py` and `retention.py` are what this plan proposes to
  extract into `skills/shared/artifact_paths.py`.
- The plan refactors `prioritize-proposals` — a working, otherwise-unrelated
  skill — to fix a defect in `audit-choices`. D4 is the guard on that.
- Canonical spec `openspec/specs/skill-workflow/spec.md` already contains the
  requirement this change modifies. Check the delta against it.
- Repo conventions are in `AGENTS.md`. The dependency-direction linter is
  `skills/validate-feature/scripts/linters/dependency_direction.py`.

## What to look for

Report only defects you can justify by pointing at a file.

1. **Verify the plan's factual claims by reading the code.** It asserts things
   about `run_audit.py`'s path derivation, `priorities_paths.py`'s exports,
   `retention.py`'s semantics, `install-manifest.json`'s `shared_libraries`
   handling, and what `skills/tests/prioritize-proposals/` currently covers.
   Check each one.
2. **D4's characterization guard.** It was strengthened during self-review to
   run CLI entry points as subprocesses from a runtime-shaped layout. Is it now
   sufficient to prove the migration changed nothing? What breakage could still
   pass it?
3. **D7 and D8 were decided without a human** and are explicitly flagged as
   overturnable. D7 names the run directory from the ledger's own header rather
   than the caller's `run_id`. D8 makes range ledgers per-run snapshots with
   retention isolated. Judge both on their merits and say if either is wrong.
4. **D6's read-only contract.** It now names three permitted effects. Is that
   set actually complete and checkable, or can a run produce a fourth?
5. **Completeness and testability.** Every scenario in the delta should have a
   task whose assertion would fail if the behavior regressed. Content
   assertions that match too loosely are findings.
6. **Scope.** The proposal claims no change to the schema, ledger format, entry
   pipeline, header, or exit-code contract. Verify nothing in the tasks violates
   that.
7. **Dependency ordering.** The task graph has a strict chain through the shared
   extraction. Check it is correct and free of file-overlap conflicts.

## Output format

Output ONLY valid JSON conforming to
`openspec/schemas/review-findings.schema.json`. No prose before or after. Each
finding requires `id` (integer), `type`, `criticality`, `axis`, `severity`,
`disposition`, and `description`; include `file_path` and `resolution`. Return
an empty findings array rather than inventing findings.
