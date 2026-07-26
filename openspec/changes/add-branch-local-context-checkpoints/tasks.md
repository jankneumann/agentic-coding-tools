# Tasks — add-branch-local-context-checkpoints

Sizing per the plan-feature Task Sizing Reference. Test tasks precede the implementation
they verify (TDD RED → GREEN). Scenarios are referenced by name; capabilities are
`pcro` = `project-context-refresh-orchestration`, `swf` = `skill-workflow`.

## Phase 1 — Report contract (wp-contracts)

- [x] 1.1 Write contract tests for the checkpoint report schema — valid document accepted;
      `namespace.kind: "main"` rejected; `checkpoint_status: "failed"` rejected;
      `context_impact.status: "unmigrated"` accepted alongside a non-empty surface list.
      **Spec scenarios**: pcro "Report validates against the checkpoint schema",
      pcro "Checkpoint indexing uses a work-package namespace"
      **Contracts**: `contracts/context-checkpoint.schema.json`
      **Design decisions**: D4 (non-canonical namespace), D7 (report location), D8 (no failed state)
      **Dependencies**: None
      **Size**: S

- [x] 1.2 Add a resolution test proving the `$ref`s into
      `context-refresh-types.schema.json` resolve once installed beside the existing
      context-refresh schemas.
      **Design decisions**: D7
      **Dependencies**: 1.1
      **Size**: S

- [x] 1.3 Install `context-checkpoint.schema.json` into `openspec/schemas/` and mirror it
      into `skills/project-context-refresh/install_assets/openspec/schemas/`.
      **Dependencies**: 1.1, 1.2
      **Size**: S

- [x] 1.4 Checkpoint: run tests, review diff, verify scope.

## Phase 2 — Index namespace and scope threading (wp-adapter)

- [x] 2.1 Write tests for namespace threading in `semantic_adapter.py` — the built argv
      carries `work_package` and the `<change-id>--<package-id>` key when a namespace is
      supplied, and still carries `main`/`main` when it is not.
      **Spec scenarios**: pcro "Checkpoint indexing uses a work-package namespace",
      pcro "Canonical refresh indexing is unchanged"
      **Design decisions**: D4
      **Dependencies**: None
      **Size**: S

- [x] 2.2 Write tests for scope threading — argv carries `--read-allow` / `--deny` from a
      resolved scope, and deny wins over an overlapping read-allow glob.
      **Spec scenarios**: pcro "Denied paths are excluded from checkpoint indexing",
      pcro "Checkpoint does not read outside the permitted scope"
      **Design decisions**: D5
      **Dependencies**: None
      **Size**: S

- [x] 2.3 Add optional namespace and scope parameters to `semantic_adapter.py`, defaulting
      to the current `main`/`main` and empty-scope behaviour.
      **Dependencies**: 2.1, 2.2
      **Size**: M

- [x] 2.4 Verify the existing `test_semantic_adapter.py` suite is unchanged and green —
      the ri-07 canonical path must not regress.
      **Dependencies**: 2.3
      **Size**: XS

- [x] 2.5 Checkpoint: run tests, review diff, verify scope.

## Phase 3 — Checkpoint module (wp-checkpoint)

- [x] 3.1 Write the ledger-isolation test — after a checkpoint run, the
      refresh-operations directory under the resolved git common dir has gained no
      entries and no manifest was written.
      **Spec scenarios**: pcro "Checkpoint leaves the shared operation ledger untouched",
      pcro "A later canonical refresh is unaffected by a prior checkpoint"
      **Design decisions**: D1, D10
      **Dependencies**: None
      **Size**: M

- [x] 3.2 Write the read-only test — a checkpoint against a dirty tree leaves every
      tracked producer output byte-identical, and producers are invoked in check mode only.
      **Spec scenarios**: pcro "Tracked producer outputs are unchanged by a checkpoint",
      pcro "Producers are invoked in check mode"
      **Design decisions**: D3
      **Dependencies**: None
      **Size**: S

- [x] 3.3 Write the determinism test — two runs at one revision produce byte-identical
      reports, and the report validates against the schema.
      **Spec scenarios**: pcro "Repeated checkpoints at one revision produce no diff"
      **Design decisions**: D7
      **Dependencies**: None
      **Size**: S

- [x] 3.4 Write the degradation test — with no index configuration the report records a
      not-configured status with a fallback, retains all deterministic findings, and the
      run still succeeds.
      **Spec scenarios**: pcro "Missing index configuration degrades the checkpoint",
      pcro "Index error does not discard deterministic findings",
      pcro "Detected drift does not fail the checkpoint"
      **Design decisions**: D8, D9
      **Dependencies**: None
      **Size**: S

- [x] 3.5 Implement `checkpoint.py` — surface inference via the ri-08 detector, producer
      dispatch through `registry.run_producer` in check mode, and report assembly.
      **Design decisions**: D1, D2, D3
      **Dependencies**: 3.1, 3.2, 3.3, 3.4
      **Size**: M

- [x] 3.6 Checkpoint: run tests, review diff, verify scope.

- [x] 3.7 Write the architecture-coverage test — a stale artifact yields
      `delta_authoritative: false`; a fresh artifact yields the changed-node list.
      **Spec scenarios**: pcro "Stale architecture artifact yields a labelled delta",
      pcro "Fresh architecture artifact yields an authoritative delta"
      **Design decisions**: D6
      **Dependencies**: 3.5
      **Size**: S

- [x] 3.8 Add architecture coverage to `checkpoint.py` — freshness via
      `run_architecture.py --check`, delta via `diff_architecture.py` against the merge base.
      **Dependencies**: 3.7
      **Size**: M

- [x] 3.9 Write the CLI test — `checkpoint` subcommand refuses a shared checkout and
      returns a non-zero exit only when no valid report could be produced.
      **Spec scenarios**: pcro "Checkpoint runs for a work package inside a feature worktree",
      pcro "Checkpoint refuses to run against a shared checkout",
      pcro "Inability to produce a report is a failure"
      **Design decisions**: D8
      **Dependencies**: 3.5
      **Size**: S

- [x] 3.10 Add the `checkpoint` subcommand to `cli.py`.
      **Dependencies**: 3.9
      **Size**: S

- [x] 3.11 Checkpoint: run tests, review diff, verify scope.

## Phase 4 — Workflow trigger (wp-workflow)

- [x] 4.1 Write the trigger tests — a context-invalidating package produces a checkpoint;
      an explicitly empty surface list does not; a missing block reports `unmigrated`
      rather than impact-free; evaluation uses the changed-file list with no git range.
      **Spec scenarios**: swf "A context-invalidating package produces a checkpoint",
      swf "A package with no context impact produces no checkpoint",
      swf "Checkpoint evaluation uses the package's changed-file list",
      swf "Missing declaration is reported as unmigrated",
      swf "Empty declaration is reported as an assertion"
      **Design decisions**: D2
      **Dependencies**: None
      **Size**: M

- [x] 4.2 Write the scope-handoff test — the workflow supplies the completed package's
      read-allow and deny globs to the checkpoint.
      **Spec scenarios**: swf "Package scope is supplied to the checkpoint"
      **Design decisions**: D5
      **Dependencies**: None
      **Size**: S

- [x] 4.3 Document the per-package checkpoint trigger in `implement-feature/SKILL.md` at
      the package-completion boundary, including the `unmigrated` reporting rule.
      **Dependencies**: 4.1, 4.2
      **Size**: M

- [x] 4.4 Checkpoint: run tests, review diff, verify scope.

## Phase 5 — Integration (wp-integration)

- [ ] 5.1 Merge work-package branches into the feature branch.
      **Dependencies**: all prior phases
      **Size**: S

- [ ] 5.2 Run the full infra skill suite and `openspec validate --strict`.
      **Dependencies**: 5.1
      **Size**: S

- [ ] 5.3 Promote `contracts/context-checkpoint.schema.json` to
      `openspec/contracts/project-context-refresh/schemas/` per the repository's
      promote-before-archive rule.
      **Dependencies**: 5.2
      **Size**: XS

- [ ] 5.4 Checkpoint: run tests, review diff, verify scope.
