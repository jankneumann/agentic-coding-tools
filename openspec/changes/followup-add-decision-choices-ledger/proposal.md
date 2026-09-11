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
though it were implemented. That requirement and its two scenarios are carried
here instead, so the canonical spec never claims behavior that does not exist.

## What Changes

Three workflow hooks, two documentation updates, and one end-to-end exercise:

- `iterate-on-implementation` gains a non-blocking audit invocation at Step 11.5.
- `validate-feature` surfaces open `needs-user` ledger entries at its human gate.
- `cleanup-feature` surfaces the same entries at its own gate.
- `docs/guides/workflow.md` documents the skill.
- The decision-index README producer gains the ledger positioning note.
- An end-to-end audit runs against an archived-change fixture, exercising every
  scenario in the parent spec delta plus the two carried here.

No change to the schema, the ledger format, the audit driver, or the skill's
read-only posture. This change is wiring and documentation only.

## Selected Approach

Carry the open Phase 3 tasks forward verbatim, preserving their numbering,
dependencies, sizes, and spec-scenario references, so the dependency graph the
parent change established stays intact and reviewable.

The alternative considered was filing each task as a standalone GitHub issue.
Rejected: `tasks.md` encodes a dependency graph (3.6 depends on 3.1, 3.2 and
3.3) and per-task spec-scenario linkage, and issues would flatten both into
prose. The parent change's own record is the right shape to carry forward.

## Impact

- Affected specs: `skill-workflow` (one ADDED requirement, two scenarios)
- Affected skills: `iterate-on-implementation`, `validate-feature`,
  `cleanup-feature`, `explore-feature` (decision-index README producer)
- Affected docs: `docs/guides/workflow.md`
- Parent change: `add-decision-choices-ledger` (archived)
