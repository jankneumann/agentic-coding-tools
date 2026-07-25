# Tasks: Add work-package context impact declarations

> Change ID: `add-work-package-context-impact-declarations`

Tests precede behavior changes. Sizes use the plan-feature attention budget.
The six surfaces map onto producers that already exist (ri-01/ri-02, ri-04,
ri-05) — this change adds planning-time declaration and detection only, never
producer execution.

## 1. Schema and template

- [ ] 1.1 (S) Write failing schema tests: `context_impact` with valid surfaces
  validates; an unknown surface is rejected; `surfaces` is required when the block
  is present; `rationale.<surface>.approved_by` rejects an empty string; a
  document with no `context_impact` still validates.
  **Spec scenarios**: skill-workflow.context-impact-schema,
  skill-workflow.context-impact-optional
  **Design decisions**: D4, D5
  **Dependencies**: none
- [ ] 1.2 (M) Add the `ContextImpact` and `ContextImpactRationale` `$defs` plus the
  optional `context_impact` property on `WorkPackage` in
  `skills/validate-packages/install_assets/openspec/schemas/work-packages.schema.json`.
  Keep `additionalProperties: false` throughout.
  **Spec scenarios**: skill-workflow.context-impact-schema
  **Design decisions**: D4, D5
  **Dependencies**: 1.1
- [ ] 1.3 (S) Add a commented `context_impact` example to
  `skills/plan-feature/install_assets/openspec/schemas/feature-workflow/templates/work-packages.yaml`,
  then run `bash skills/install.sh --mode rsync --force --deps none --python-tools none`
  so the `openspec/schemas/` copies regenerate.
  **Dependencies**: 1.2

- [ ] Checkpoint: `skills/tests/install_sh/test_openspec_assets.py` green; both
  schema copies byte-identical

## 2. Impact rule table

- [ ] 2.1 (S) Write failing tests for the loader: every surface in `SURFACES` has
  at least one rule; a rule naming an unknown surface fails loading; a missing rule
  file raises rather than yielding an empty rule set.
  **Spec scenarios**: skill-workflow.context-impact-rule-integrity
  **Design decisions**: D2
  **Dependencies**: none
- [ ] 2.2 (M) Add
  `skills/validate-packages/install_assets/openspec/schemas/context-impact-rules.yaml`
  mapping globs to the six surfaces, and `load_rules()` in
  `skills/validate-packages/scripts/context_impact.py`.
  **Spec scenarios**: skill-workflow.context-impact-rule-integrity
  **Design decisions**: D2
  **Dependencies**: 2.1

## 3. Detector

- [ ] 3.1 (S) Write failing tests for `infer_surfaces`: each of the six surfaces is
  inferred from a representative path; a changed file outside
  `scope.write_allow` is excluded; a file listed in `contracts.openapi.files`
  implies `apis`.
  **Spec scenarios**: skill-workflow.context-impact-inference
  **Design decisions**: D1, D6
  **Dependencies**: 2.2
- [ ] 3.2 (M) Implement `infer_surfaces(package, changed_files, rules, contract_files)`
  and `declared_surfaces(package)` in `context_impact.py`. Take changed files as a
  sequence; do not shell out to git.
  **Spec scenarios**: skill-workflow.context-impact-inference
  **Design decisions**: D1, D6
  **Dependencies**: 3.1
- [ ] 3.3 (S) Write failing tests for `index_scopes`: returns the package's
  `read_allow` and `deny`; a path matching both resolves denied.
  **Spec scenarios**: skill-workflow.context-impact-index-scopes
  **Design decisions**: D8
  **Dependencies**: 3.2
- [ ] 3.4 (S) Implement `index_scopes(package)` returning the resolved read scope
  with `deny` precedence, adding no schema fields.
  **Spec scenarios**: skill-workflow.context-impact-index-scopes
  **Design decisions**: D8
  **Dependencies**: 3.3

- [ ] Checkpoint: detector unit tests pass on fixtures with no git repository

## 4. Enforcement gate

- [ ] 4.1 (M) Write failing tests covering every row of the D3 enforcement table:
  `declared`, `rationalized`, `undeclared`, `spurious_rationale`, `unmigrated`
  (default and `--strict-legacy`), and an empty `surfaces: []` treated strictly.
  **Spec scenarios**: skill-workflow.context-impact-undeclared,
  skill-workflow.context-impact-rationale,
  skill-workflow.context-impact-empty-declaration,
  skill-workflow.context-impact-unmigrated
  **Design decisions**: D3, D4, D5
  **Dependencies**: 3.4
- [ ] 4.2 (M) Implement `evaluate(package, changed_files, rules, contract_files)`
  returning a `ContextImpactResult` with the status, implied set, undeclared set,
  and the changed files that implied each surface.
  **Spec scenarios**: skill-workflow.context-impact-undeclared,
  skill-workflow.context-impact-rationale
  **Design decisions**: D3
  **Dependencies**: 4.1
- [ ] 4.3 (M) Add `skills/validate-packages/scripts/validate_context_impact.py`:
  resolves changed files via `git diff --name-only <base>...HEAD`, supports
  `--base`, `--strict-legacy`, and `--json`, and exits 1 on `undeclared` or
  `spurious_rationale`.
  **Spec scenarios**: skill-workflow.context-impact-undeclared,
  skill-workflow.context-impact-unmigrated
  **Design decisions**: D3, D7
  **Dependencies**: 4.2

- [ ] Checkpoint: run the new CLI against this change's own `work-packages.yaml`
  and confirm it reports `declared`

## 5. Compatibility and documentation

- [ ] 5.1 (M) Write a compatibility test asserting that no
  `openspec/changes/**/work-packages.yaml` in the repository gains a schema error
  mentioning `context_impact`. 24 of 62 such files are already schema-invalid on
  baseline (see D9), so "everything validates" is not a passable assertion —
  the gate must isolate *new* constraints introduced by this change.
  **Spec scenarios**: skill-workflow.context-impact-optional
  **Design decisions**: D3, D9
  **Dependencies**: 1.2
- [ ] 5.2 (S) Document the surfaces, the enforcement table, and the new CLI in
  `skills/validate-packages/SKILL.md`.
  **Dependencies**: 4.3
- [ ] 5.3 (S) Dogfood the gate: add a `context_impact` block to this change's own
  `work-packages.yaml`. Confirm the gate reports `unmigrated` before the block is
  added and `declared` after, which proves both enforcement branches on real data.
  **Spec scenarios**: skill-workflow.context-impact-unmigrated,
  skill-workflow.context-impact-undeclared
  **Design decisions**: D3
  **Dependencies**: 5.2

- [ ] Checkpoint: full infra suite green; `openspec validate --strict
  add-work-package-context-impact-declarations` passes
