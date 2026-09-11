# Change: followup-add-decision-choices-ledger

## Why

`add-decision-choices-ledger` shipped Phases 1 and 2: the decision-choices
schema, the evidence collector and cross-reference resolver, the ledger writer
and renderer, the audit driver, and the `audit-choices` skill. Those landed on
`main` in PR #411 and are archived.

Phase 3 did not ship. It is the phase that connects the skill to the lifecycle:
without it, `audit-choices` exists and is fully tested, but nothing invokes it
and no gate surfaces what it produces. The capability is built and unreachable.

Archiving the parent change with Phase 3 open would have promoted the
"Choices audit workflow integration" requirement into `openspec/specs/` as
though it were implemented. That requirement and its scenarios are carried
here instead, so the canonical spec never claims behavior that does not exist.

## What Changes

Three workflow hooks, one read-only reader, two documentation updates, and the
tests that pin them:

- `iterate-on-implementation` gains a non-blocking audit invocation at a new
  Step 11.5 (after vendor-review remediation, before the summary) that also
  commits the resulting ledger pair when it changed.
- `validate-feature` surfaces open `needs-user` ledger entries as a `Choices:`
  row in its Step 11 validation report, echoed at the After Validation prompt.
- `cleanup-feature` surfaces the same entries at a new Step 5.5, after open
  tasks are migrated and before archive.
- `skills/audit-choices/scripts/needs_user.py` — a read-only reader both gates
  call, so the `needs-user` filter and least-confident-first ordering live in
  one tested place instead of two SKILL.md snippets.
- `docs/guides/workflow.md` documents the skill.
- The decision-index README producer gains the ledger positioning note, with
  `docs/decisions/README.md` regenerated in the same commit.
- `skills/audit-choices/SKILL.md` documents an optional `--run-id` argument so
  the Step 11.5 hook can name the run that produced a ledger. `run_audit.py`
  has required `--run-id` since Phase 2; only the Arguments section was
  missing it. With the reader above, that is the whole of what this change
  touches inside `audit-choices`: one new read-only script, one documented
  argument, no new writer.
- An end-to-end pytest drives the audit against a fixture repo seeded from the
  archived parent change's artifacts, exercising every scenario in the parent
  spec delta plus the five carried or added here; a second test pins the three
  SKILL.md hooks.

No change to the schema, the ledger format, the audit driver, `gate_logic.py`,
or the skill's read-only posture. Both gate hooks are SKILL.md steps that
shell out to the reader, so no validation or cleanup code path is touched; the
reader opens no file for writing and the mechanical read-only test is
unchanged. The one edit inside `audit-choices` is the Arguments documentation
above. Decisions specific to this change (hook placement, ledger commit
policy, report-row form, fixture strategy, failure semantics, scenario
ordinals, the `--run-id` contract) are recorded in `design.md` as F1–F8; the
parent's D1–D8 stand unchanged.

## Selected Approach

Carry the open Phase 3 tasks forward verbatim, preserving their numbering,
dependencies, sizes, and spec-scenario references, so the dependency graph the
parent change established stays intact and reviewable. Plan iteration added
two tasks (3.0 reader, 3.7 hook tests) and three scenarios (cleanup gate,
absent ledger, standalone range) where the carried set left a requirement
clause or an implementing task without a scenario; see `plan-findings.md`.

The alternative considered was filing each task as a standalone GitHub issue.
Rejected: `tasks.md` encodes a dependency graph (3.6 depends on 3.0; 3.7 on
3.1–3.3) and
per-task spec-scenario linkage, and issues would flatten both into prose. The
parent change's own record is the right shape to carry forward.

## Impact

- Affected specs: `skill-workflow` (one ADDED requirement, five scenarios)
- Affected skills: `iterate-on-implementation`, `validate-feature`,
  `cleanup-feature`, `audit-choices` (new reader script, no driver change),
  `explore-feature` (decision-index README producer)
- Affected docs: `docs/guides/workflow.md`, `docs/decisions/README.md`
  (regenerated)
- Affected tests: `skills/tests/audit-choices/` (three new files; directory
  already registered in `testpaths`)
- Parent change: `add-decision-choices-ledger` (archived)
- Out of scope, recommended follow-up: the standalone `range:<base>..<head>`
  form writes its ledger under `openspec/changes/range:.../` (Phase 2 quirk)
