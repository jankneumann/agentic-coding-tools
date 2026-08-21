# skill-workflow — Decision Choices Ledger

## ADDED Requirements

### Requirement: Choices ledger artifact pair

Each change MAY carry a choices ledger recording implementation-time decisions
made where the spec was silent. When present, the ledger SHALL consist of
`openspec/changes/<change-id>/choices.json` (machine-readable source of truth,
valid against `openspec/schemas/decision-choices.schema.json`) and
`openspec/changes/<change-id>/choices.md` (human-readable rendering derived
from the JSON). `choices.json` SHALL carry the six-field codeviz artifact
header (`schema_version`, `generated_at`, `git_sha`, `generator`, `run_id`,
`event_kind`). The artifact SHALL be optional: its absence MUST NOT fail
validation or block archive.

#### Scenario: Ledger pair is schema-valid

- WHEN an audit run completes for a change
- THEN `choices.json` SHALL validate against
  `openspec/schemas/decision-choices.schema.json`
- AND the artifact header SHALL contain all six required fields
- AND `choices.md` SHALL be regenerated from `choices.json` in the same run

#### Scenario: Missing ledger does not block archive

- WHEN a change without a `choices.json` reaches validation or archive
- THEN validation SHALL NOT fail on the missing artifact
- AND archive SHALL proceed without it

### Requirement: Independent read-only choices audit

The choices ledger SHALL be produced by an auditor pass that is independent of
the implementing agent: a separately dispatched sub-agent whose input is the
change's git history (`git log` / `git diff` over the change branch) and its
planning artifacts (`proposal.md`, `design.md`, spec deltas, `session-log.md`,
`impl-findings.md` when present). The auditor MUST NOT modify any file outside
`openspec/changes/<change-id>/choices.json` and `choices.md`, MUST NOT write to
`session-log.md`, `docs/decisions/`, or any source file, and MUST exit with
status 0 regardless of the verdicts recorded.

#### Scenario: Auditor writes only the ledger pair

- WHEN the audit-choices skill runs against a change
- THEN the only files created or modified SHALL be
  `openspec/changes/<change-id>/choices.json` and
  `openspec/changes/<change-id>/choices.md`
- AND a snapshot comparison of the rest of the working tree SHALL show no
  changes

#### Scenario: Adverse verdicts never block

- WHEN the audit records entries with verdict `unsound` or `needs-user`
- THEN the audit process SHALL still exit with status 0
- AND no workflow step SHALL be halted by the audit itself

### Requirement: Choices ledger entry content

Each ledger entry SHALL record: the choice (headline plus a concrete scenario),
the gap (what the spec or design left unspecified), the reach (what the choice
constrains or enables for future work), a verdict (`sound`, `unsound`, or
`needs-user`) with rationale, a confidence level (`low`, `medium`, or `high`),
and provenance (commit range and touched files). Each entry SHALL carry a
content-derived `stable_id` so that re-running the audit is idempotent for
unchanged decisions. Each entry SHALL either cross-reference the matching
self-reported decision as `<change-id>#D<n>` (optionally phase-qualified) or
be flagged `self_reported: false` when the implementer did not report it.

#### Scenario: Unreported decision is flagged

- WHEN the auditor identifies a decision in the diff that has no matching
  `Decisions` bullet in the change's `session-log.md`
- THEN the ledger entry SHALL set `self_reported: false`
- AND the entry SHALL still include gap, reach, verdict, and confidence

#### Scenario: Re-audit is idempotent

- WHEN the audit runs twice over the same commit range with no new commits
- THEN entries for unchanged decisions SHALL keep the same `stable_id`
- AND no duplicate entries SHALL be appended

### Requirement: Least-confident-first ranking

The rendered `choices.md` SHALL order entries ascending by confidence
(`low` before `medium` before `high`), and within equal confidence SHALL order
verdicts `needs-user`, then `unsound`, then `sound`. The ranking SHALL be a
property of the renderer so it can be verified by a unit test against
`choices.json` fixtures.

#### Scenario: Rendering enforces the ranking invariant

- WHEN `choices.md` is rendered from a `choices.json` containing mixed
  confidence levels
- THEN the first entry SHALL be a lowest-confidence entry
- AND no entry SHALL appear before another entry of strictly lower confidence

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
