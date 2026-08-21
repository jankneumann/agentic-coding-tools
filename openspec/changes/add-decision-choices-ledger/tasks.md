# Tasks: add-decision-choices-ledger

## Phase 1 — Schema and artifact registration

- [x] 1.1 Write tests for the decision-choices JSON schema
  **Spec scenarios**: skill-workflow.1 (Ledger pair is schema-valid), skill-workflow.3 (Unreported decision is flagged)
  **Contracts**: openspec/schemas/decision-choices.schema.json
  **Design decisions**: D1, D4
  **Dependencies**: None
  **Size**: S
- [x] 1.2 Add openspec/schemas/decision-choices.schema.json
  **Design decisions**: D1, D3, D4
  **Dependencies**: 1.1
  **Size**: S
- [x] 1.3 Register the choices artifact in feature-workflow schema.yaml
  **Design decisions**: D8
  **Dependencies**: 1.2
  **Size**: XS
- [x] 1.4 Add templates/choices.md to feature-workflow templates
  **Dependencies**: 1.3
  **Size**: XS
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 1.5 Mirror schema.yaml plus template into plan-feature install_assets
  **Design decisions**: D8
  **Dependencies**: 1.3, 1.4
  **Size**: XS
- [x] 1.6 Add a choices rules block to openspec/config.yaml
  **Dependencies**: 1.3
  **Size**: XS

## Phase 2 — Auditor skill

- [x] 2.1 Write tests for the ledger writer plus renderer
  **Spec scenarios**: skill-workflow.4 (Re-audit is idempotent), skill-workflow.5 (Rendering enforces the ranking invariant)
  **Contracts**: openspec/schemas/decision-choices.schema.json
  **Design decisions**: D2, D3
  **Dependencies**: 1.2
  **Size**: S
- [x] 2.2 Create skills/audit-choices/scripts/choices_ledger.py
  **Design decisions**: D2, D3, D4
  **Dependencies**: 2.1
  **Size**: M
- [x] 2.3 Create the choices.md renderer in choices_ledger.py
  **Design decisions**: D2
  **Dependencies**: 2.2
  **Size**: S
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.4 Write tests for the evidence collector
  **Spec scenarios**: skill-workflow.2 (Auditor writes only the ledger pair)
  **Design decisions**: D5, D7
  **Dependencies**: 1.2
  **Size**: S
- [ ] 2.5 Create skills/audit-choices/scripts/collect_evidence.py
  **Design decisions**: D5, D7
  **Dependencies**: 2.4
  **Size**: M
- [ ] 2.6 Create the session-log cross-reference resolver in collect_evidence.py
  **Spec scenarios**: skill-workflow.3 (Unreported decision is flagged)
  **Design decisions**: D5
  **Dependencies**: 2.5
  **Size**: S
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 2.7 Write the read-only posture test for the audit driver
  **Spec scenarios**: skill-workflow.2 (Auditor writes only the ledger pair), skill-workflow.6 (Adverse verdicts never block)
  **Design decisions**: D6, D7
  **Dependencies**: 2.5
  **Size**: S
- [ ] 2.8 Create skills/audit-choices/SKILL.md
  **Design decisions**: D6, D7
  **Dependencies**: 2.2, 2.5, 2.7
  **Size**: M

## Phase 3 — Workflow hooks and documentation

- [ ] 3.1 Add the Step 11.5 audit invocation to iterate-on-implementation
  **Spec scenarios**: skill-workflow.7 (Workflow invocation is non-blocking)
  **Design decisions**: D6
  **Dependencies**: 2.8
  **Size**: S
- [ ] 3.2 Surface needs-user ledger entries at the validate-feature gate
  **Spec scenarios**: skill-workflow.8 (needs-user entries surface at the validation gate)
  **Design decisions**: D6
  **Dependencies**: 2.8
  **Size**: S
- [ ] 3.3 Surface needs-user ledger entries at the cleanup-feature gate
  **Design decisions**: D6
  **Dependencies**: 2.8
  **Size**: S
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.4 Update docs/guides/workflow.md with the audit-choices skill
  **Dependencies**: 2.8
  **Size**: XS
- [ ] 3.5 Add the ledger positioning note at the decision-index README producer
  **Design decisions**: D5
  **Dependencies**: 2.8
  **Size**: S
- [ ] 3.6 Run an end-to-end audit against an archived-change fixture
  **Spec scenarios**: skill-workflow.1 through skill-workflow.8
  **Dependencies**: 3.1, 3.2, 3.3
  **Size**: M
- [ ] Checkpoint: run tests, review diff, verify scope
