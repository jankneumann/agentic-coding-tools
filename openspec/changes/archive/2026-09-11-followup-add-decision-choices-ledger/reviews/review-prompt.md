# Plan Review — followup-add-decision-choices-ledger

You are an independent plan reviewer. Review the OpenSpec proposal artifacts for
change `followup-add-decision-choices-ledger`. This is a PLAN review, not a code
review: judge the plan, not an implementation (none exists yet).

## Read these files (all paths relative to the repository root)

- `openspec/changes/followup-add-decision-choices-ledger/proposal.md`
- `openspec/changes/followup-add-decision-choices-ledger/design.md`
- `openspec/changes/followup-add-decision-choices-ledger/tasks.md`
- `openspec/changes/followup-add-decision-choices-ledger/specs/skill-workflow/spec.md`
- `openspec/changes/followup-add-decision-choices-ledger/plan-findings.md` (prior self-review; do not simply repeat it)

## Context you will need

The parent change is archived at
`openspec/changes/archive/2026-09-10-add-decision-choices-ledger/` — its
`design.md` defines decisions D1..D9 and its spec delta defines scenarios
skill-workflow.1 through .6. The shipped skill under review-by-wiring is
`skills/audit-choices/` (driver `scripts/run_audit.py`, ledger helpers
`scripts/choices_ledger.py`, tests under `skills/tests/audit-choices/`).

The three workflow hooks the plan proposes to add live in:
- `skills/iterate-on-implementation/SKILL.md` (new Step 11.5)
- `skills/validate-feature/SKILL.md` (Step 11 Phase Results row)
- `skills/cleanup-feature/SKILL.md` (new Step 5.5, before `### 6. Archive OpenSpec Proposal`)
- `skills/explore-feature/scripts/decision_index.py` (`emit_readme`)
- `docs/guides/workflow.md`

Repository conventions that matter here are in `AGENTS.md`, especially the
OpenSpec path-stability rule: a test must never pin
`openspec/changes/<change-id>/` or an archive path as a literal — it resolves
the directory at read time.

## What to look for

Evaluate across these axes and report only defects you can justify:

1. **Completeness** — requirements without scenarios, hooks without tasks,
   tasks without verification, unaddressed failure modes.
2. **Correctness of the plan's factual claims** — verify claims about the
   existing code by reading it. The plan asserts things about `run_audit.py`
   range handling, `gate_logic.py` section parsing, `choices_ledger.rank_entries`,
   and the exact heading structure of the three target SKILL.md files. Check them.
3. **Feasibility** — can each task be done as written, with the files named?
4. **Testability** — are the assertions in tasks 3.0, 3.6 and 3.7 actually
   checkable, and do they cover the scenarios they claim to cover?
5. **Consistency** — proposal vs design vs tasks vs spec delta; the scenario
   key table's ordinals vs the real scenarios in both spec files.
6. **Scope** — anything the plan changes that the proposal says it will not
   (it claims no schema, ledger-format, driver, or read-only-posture change).
7. **Dependency graph** — is the stated task ordering correct and free of
   file-overlap conflicts?

## Output format

Output ONLY valid JSON conforming to
`openspec/schemas/review-findings.schema.json`. No prose before or after the
JSON. Each finding needs a stable `id`, `criticality`
(low/medium/high/critical), `type`, a `summary`, the `file` it concerns, and a
concrete `recommendation`. If you find no defects at a criticality, return an
empty findings array rather than inventing findings.
