# skill-workflow — Choices Audit Workflow Integration

## ADDED Requirements

### Requirement: Choices audit workflow integration

The implementation workflow SHALL invoke the choices audit non-blockingly after
its converged review step and before its final summary, and the audit SHALL
also be invocable standalone against any change id or commit range. Validation
and cleanup gates SHALL surface open `needs-user` entries from the ledger at
their existing human decision points, in the same manner deferred tasks are
surfaced; they MUST NOT introduce a new blocking gate for the audit.

#### Scenario: Workflow invocation is non-blocking

- WHEN `iterate-on-implementation` completes its convergence loop and the
  choices audit fails or is unavailable
- THEN the workflow SHALL log the failure and continue to its summary step

#### Scenario: needs-user entries surface at the validation gate

- WHEN `validate-feature` reaches its human gate and the change's ledger
  contains entries with verdict `needs-user`
- THEN those entries SHALL be listed in the gate presentation
- AND the gate's approve/reject semantics SHALL otherwise remain unchanged
