# Tasks: followup-add-decision-choices-ledger

Carried forward from `add-decision-choices-ledger` Phase 3 on 2026-09-11 at
cleanup time. Numbering, dependencies, sizes and spec-scenario references are
preserved from the parent change so the dependency graph stays intact.

Dependencies on parent task `2.8` (create `skills/audit-choices/SKILL.md`) are
satisfied: that task is complete and archived.

## Phase 3 — Workflow hooks and documentation

- [ ] 3.1 Add the Step 11.5 audit invocation to iterate-on-implementation
  **Spec scenarios**: skill-workflow.7 (Workflow invocation is non-blocking)
  **Design decisions**: D6
  **Dependencies**: none (parent 2.8 archived)
  **Size**: S
- [ ] 3.2 Surface needs-user ledger entries at the validate-feature gate
  **Spec scenarios**: skill-workflow.8 (needs-user entries surface at the validation gate)
  **Design decisions**: D6
  **Dependencies**: none (parent 2.8 archived)
  **Size**: S
- [ ] 3.3 Surface needs-user ledger entries at the cleanup-feature gate
  **Design decisions**: D6
  **Dependencies**: none (parent 2.8 archived)
  **Size**: S
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.4 Update docs/guides/workflow.md with the audit-choices skill
  **Dependencies**: none (parent 2.8 archived)
  **Size**: XS
- [ ] 3.5 Add the ledger positioning note at the decision-index README producer
  **Design decisions**: D5
  **Dependencies**: none (parent 2.8 archived)
  **Size**: S
- [ ] 3.6 Run an end-to-end audit against an archived-change fixture
  **Spec scenarios**: skill-workflow.1 through skill-workflow.8
  **Dependencies**: 3.1, 3.2, 3.3
  **Size**: M
- [ ] Checkpoint: run tests, review diff, verify scope
