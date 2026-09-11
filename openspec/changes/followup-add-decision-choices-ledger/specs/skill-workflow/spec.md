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
  choices audit fails (the driver reports an internal error or the step
  raises) or is unavailable (the skill is not installed, or no independent
  sub-agent can be dispatched)
- THEN the workflow SHALL log a single warning naming the reason
- AND SHALL continue to its summary step with a non-failing outcome
- AND the workflow SHALL NOT commit a partial ledger pair: when only one of
  `choices.json` and `choices.md` was produced, the workflow SHALL treat the
  audit as failed and leave neither file staged

#### Scenario: needs-user entries surface at the validation gate

- WHEN `validate-feature` reaches its human gate and the change's ledger
  contains entries with verdict `needs-user`
- THEN each such entry SHALL be listed in the gate presentation with its
  `stable_id`, confidence and choice headline, least-confident first
- AND the validation result (`PASS`/`FAIL`) SHALL be the same as it would be
  without the ledger
- AND the gate's approve/reject semantics SHALL otherwise remain unchanged

#### Scenario: needs-user entries surface at the cleanup gate

- WHEN `cleanup-feature` reaches its pre-archive decision point and the
  change's ledger contains entries with verdict `needs-user`
- THEN each such entry SHALL be listed with its `stable_id`, confidence and
  choice headline, least-confident first
- AND archive SHALL proceed on the user's existing confirmation without an
  additional gate
- AND the entries SHALL be archived unchanged with the change directory

#### Scenario: Absent or empty ledger is silent at the gates

- WHEN `validate-feature` or `cleanup-feature` reaches its decision point and
  the change has no `choices.json`, or has one with no `needs-user` entries
- THEN the presentation SHALL state that no open choices exist
- AND neither skill SHALL fail, warn, or prompt on the missing entries

#### Scenario: Standalone invocation against a commit range

- WHEN the audit is invoked with a single `<base-sha>..<head-sha>` argument
  and no change directory
- THEN the invocation SHALL derive the audited base and head from that
  argument rather than from a change directory
- AND the ledger's recorded `change_id` SHALL be `range:<base-sha>..<head-sha>`
- AND the driver SHALL exit with status 0
