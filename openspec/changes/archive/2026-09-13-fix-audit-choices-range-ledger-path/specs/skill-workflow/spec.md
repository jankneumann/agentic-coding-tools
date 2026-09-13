# skill-workflow — Standalone range audits write outside the changes tree

## MODIFIED Requirements

### Requirement: Choices audit workflow integration

The implementation workflow SHALL invoke the choices audit non-blockingly after
its converged review step and before its final summary, and the audit SHALL
also be invocable standalone against any change id or commit range. Validation
and cleanup gates SHALL surface open `needs-user` entries from the ledger at
their existing human decision points, in the same manner deferred tasks are
surfaced; they MUST NOT introduce a new blocking gate for the audit.

A standalone commit-range audit SHALL NOT write into `openspec/changes/`. Its
ledger pair SHALL be persisted under a run-scoped directory dedicated to
standalone audits, and the audited range SHALL be recoverable from the ledger's
own contents rather than from the path it was written to.

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
- THEN the presentation SHALL say so explicitly, in that gate's own
  established form, rather than omitting the subject
- AND the two cases SHALL be distinguishable from each other: "no ledger" and
  "a ledger with nothing open" MUST NOT render identically
- AND neither skill SHALL fail, warn, or prompt on the missing entries

#### Scenario: Standalone invocation against a commit range

- WHEN `/audit-choices` is invoked with a single `<base-sha>..<head-sha>`
  argument and no change directory
- THEN the skill SHALL take the audited base and head from that argument
  rather than resolving them from a change's base commit
- AND the ledger it persists SHALL record `change_id` as
  `range:<base-sha>..<head-sha>`
- AND the ledger pair SHALL be written to a run-scoped directory outside
  `openspec/changes/`, leaving no directory named after the commit range
- AND `audited_range` SHALL carry both full shas, so the audited range is
  recoverable without reading the path
- AND `latest.json` and `latest.md` at the standalone-audit root SHALL be
  updated to copies of that run's pair, so the most recent standalone audit is
  reachable without knowing its run id
- AND the driver SHALL exit with status 0

#### Scenario: A change-id audit is unaffected by the range-form destination

- WHEN `/audit-choices` is invoked with a change id
- THEN the ledger pair SHALL be written to
  `openspec/changes/<change-id>/choices.json` and `choices.md`, exactly as
  before
- AND no file SHALL be written under the standalone-audit directory

#### Scenario: Standalone audit output is bounded

- WHEN the number of run directories under the standalone-audit root exceeds
  the configured retention count
- THEN the oldest of those run directories SHALL be moved to an archive
  subdirectory of that root rather than deleted
- AND no run's ledger pair SHALL be destroyed by retention
- AND a retention failure SHALL NOT change the outcome of a run whose ledger
  pair was written: the run SHALL still report success with both paths set

### Requirement: Independent read-only choices audit

The choices ledger SHALL be produced by an auditor pass that is independent of
the implementing agent: a separately dispatched sub-agent whose input is the
change's git history (`git log` / `git diff` over the change branch) and its
planning artifacts (`proposal.md`, `design.md`, spec deltas, `session-log.md`,
`impl-findings.md` when present). The auditor MUST NOT write to
`session-log.md`, `docs/decisions/`, or any source file, and MUST exit with
status 0 regardless of the verdicts recorded.

The set of files the auditor may create or modify depends on which form it was
invoked in, and is closed in both. For a change-id audit it is
`openspec/changes/<change-id>/choices.json` and `choices.md`. For a standalone
commit-range audit it is that run's ledger pair under the standalone-audit
root, the `latest.json` and `latest.md` copies at that root, and the archive
move retention performs. Nothing else, in either form.

#### Scenario: Auditor writes only the ledger pair

- WHEN the audit-choices skill runs against a change
- THEN the only files created or modified SHALL be
  `openspec/changes/<change-id>/choices.json` and
  `openspec/changes/<change-id>/choices.md`
- AND a snapshot comparison of the rest of the working tree SHALL show no
  changes

#### Scenario: A standalone audit writes only its run directory and the latest pointers

- WHEN the audit-choices skill runs in its standalone commit-range form
- THEN the only files created or modified SHALL be that run's `choices.json`
  and `choices.md`, the `latest.json` and `latest.md` copies at the
  standalone-audit root, and any archive move retention performs
- AND a snapshot comparison of the rest of the working tree SHALL show no
  changes, including no file under `openspec/changes/`

#### Scenario: Adverse verdicts never block

- WHEN the audit records entries with verdict `unsound` or `needs-user`
- THEN the audit process SHALL still exit with status 0
- AND no workflow step SHALL be halted by the audit itself
