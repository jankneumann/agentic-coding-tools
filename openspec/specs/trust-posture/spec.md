# trust-posture Specification

## Purpose
TBD - created by archiving change add-trust-posture-contract-file. Update Purpose after archive.
## Requirements
### Requirement: Trust Posture Contract File

The system SHALL support a repo-owned trust posture contract at
`<repo_root>/TRUST_POSTURE.md` consisting of a leading YAML front-matter block
(fenced by `---`) followed by human-readable prose. The front matter SHALL declare
`schema_version: 1` and a `gates` mapping. The repository SHALL ship a documented
template at `<repo_root>/TRUST_POSTURE.template.md` (not the active path) in which
every gate's disposition is `block`. The contract SHALL be validated by the schema at
`openspec/schemas/trust-posture.schema.json`, whose gate keys are the eight enumerated
gates.

The eight gates SHALL be representable: `gatekeeper_escalation`, `proposal_approval`,
`plan_review_convergence_failure`, `validation_failure`, `escalate_resume`,
`replan_required`, `pr_creation`, and `merge`.

Each gate SHALL declare a `disposition` of `auto`, `notify_with_timeout`, or `block`.
A gate with disposition `notify_with_timeout` SHALL additionally declare
`timeout_seconds` (a positive integer) and `default_action` (`proceed` or `block`).
`timeout_seconds` and `default_action` SHALL NOT be present on a gate whose disposition
is `auto` or `block`.

#### Scenario: Valid contract loads

- **WHEN** a `TRUST_POSTURE.md` with valid front matter is loaded
- **THEN** the loader SHALL return a posture reporting `present` is true
- **AND** each configured gate SHALL resolve to its declared disposition, timeout, and default action

#### Scenario: All eight gates representable

- **WHEN** the shipped `TRUST_POSTURE.template.md` is validated
- **THEN** validation SHALL succeed
- **AND** all eight enumerated gates SHALL be present and resolvable through the loader

#### Scenario: Each disposition round-trips

- **WHEN** a gate declares `auto`, `block`, `notify_with_timeout` with `default_action: proceed`, or `notify_with_timeout` with `default_action: block`
- **THEN** the loader SHALL resolve that gate to a disposition object equal to the declared configuration in every field

### Requirement: Absent Contract Fails Closed To Block

When no `TRUST_POSTURE.md` file is present, loading the trust posture SHALL succeed and
return a posture in which every one of the eight gates resolves to the `block`
disposition, byte-identical to the pre-contract behavior. A posture loaded from an
absent file SHALL report `present` as false so consumers can distinguish it from a
loaded all-block posture. A gate that is omitted from a present contract SHALL likewise
resolve to `block` (fail-closed).

#### Scenario: No contract file present

- **WHEN** the trust posture is loaded and no `TRUST_POSTURE.md` exists at the repo root
- **THEN** loading SHALL NOT raise
- **AND** `disposition_for` SHALL return `block` for every one of the eight gates
- **AND** the posture SHALL report `present` is false

#### Scenario: Gate omitted from a present contract

- **WHEN** a present contract configures some gates but omits others
- **THEN** each omitted gate SHALL resolve to `block`

### Requirement: Contract Validation Rejects Malformed Contracts

Loading a present-but-invalid contract SHALL raise a validation error that reports every
detected problem in a single pass. Validation SHALL reject: an unknown gate name; an
unknown disposition value; a `notify_with_timeout` gate whose `timeout_seconds` is
missing, non-integer, boolean, zero, or negative; a `notify_with_timeout` gate whose
`default_action` is missing or not one of `proceed`/`block`; a `timeout_seconds` or
`default_action` present on an `auto` or `block` gate; an unsupported `schema_version`;
and a missing or unterminated front-matter fence. A validation-only entry point SHALL
report errors as a list without raising so tooling can consume them.

#### Scenario: Unknown gate fails

- **WHEN** a contract declares a gate name not in the eight enumerated gates
- **THEN** validation SHALL fail with an error naming the unknown gate

#### Scenario: Unknown disposition fails

- **WHEN** a gate declares a disposition other than `auto`, `notify_with_timeout`, or `block`
- **THEN** validation SHALL fail with an error naming the unknown disposition

#### Scenario: Notify gate missing or malformed timeout fails

- **WHEN** a `notify_with_timeout` gate omits `timeout_seconds` or declares a non-positive, non-integer, or boolean value
- **THEN** validation SHALL fail with an error naming `timeout_seconds`

#### Scenario: Notify gate missing default action fails

- **WHEN** a `notify_with_timeout` gate omits `default_action` or declares a value other than `proceed` or `block`
- **THEN** validation SHALL fail with an error naming `default_action`

#### Scenario: Timeout on a non-notify gate fails

- **WHEN** a gate with disposition `auto` or `block` declares `timeout_seconds` or `default_action`
- **THEN** validation SHALL fail indicating those fields are only valid for `notify_with_timeout`

### Requirement: Loader API For Downstream Consumers

The system SHALL expose a side-effect-free loader library at
`skills/shared/trust_posture.py` that downstream services (the approval gate service)
consume. It SHALL provide `load_posture(repo_root=None, *, path=None)` returning a
`TrustPosture`; `TrustPosture.disposition_for(gate)` returning a `GateDisposition` with
`disposition`, `timeout_seconds`, and `default_action` fields; `validate_posture_file`
returning a list of error strings; and `Gate`, `Disposition`, and `DefaultAction`
enumerations. `load_posture` SHALL read the contract file fresh on each call so edits are
observed without a restart. `disposition_for` SHALL raise on a gate name outside the
eight enumerated gates.

#### Scenario: Loader reads fresh each call

- **WHEN** `load_posture` is called after the contract file changes on disk
- **THEN** the returned posture SHALL reflect the current file contents without any cache invalidation step

#### Scenario: Disposition requested for unknown gate name

- **WHEN** `disposition_for` is called with a gate name outside the eight enumerated gates
- **THEN** it SHALL raise rather than return a default disposition

#### Scenario: Timeout fields populated only for notify disposition

- **WHEN** a resolved gate disposition is `notify_with_timeout`
- **THEN** its `timeout_seconds` and `default_action` SHALL be non-null
- **AND** for `auto` and `block` dispositions both SHALL be null

### Requirement: Roadmap-Approval-Scoped Auto Dispositions

The trust posture SHALL let the `proposal_approval` and `replan_required` gate configs declare an optional `unscoped` sub-config (`disposition` of `notify_with_timeout` or `block`, with the same `timeout_seconds` / `default_action` rules as a gate config), defaulting to `{disposition: block}` when absent. When either gate's disposition is `auto`, the approval gate SHALL apply `auto` only if the current launch marker, obtained by the gate through its `marker_reader` seam, carries a `roadmap_approval_ref`, and SHALL ignore any `roadmap_approval_ref` supplied in the evaluation context; otherwise it SHALL apply the `unscoped` config and record `scope: unscoped` and a reason naming the fallback in the decision. `unscoped` with disposition `auto`, or on any other gate, SHALL be a validation error. The loader SHALL also expose `posture_digest(posture)`: the SHA-256 of the canonical JSON of the parsed `gates` map, with a fixed value for the absent-posture default.

#### Scenario: Dispatched run with a valid approval reference proceeds
- **WHEN** `proposal_approval` is `auto` and `marker_reader` returns a marker carrying `roadmap_approval_ref`
- **THEN** the decision SHALL be `proceed` with `resolution: auto` and `scope: roadmap_approval`

#### Scenario: Standalone run falls back to the unscoped disposition
- **WHEN** `proposal_approval` is `auto`, no `unscoped` is declared, and `marker_reader` returns None
- **THEN** the decision SHALL be `blocked` with `resolution: posture_block`, `scope: unscoped`, and a reason containing `unscoped fallback`

#### Scenario: Declared notify fallback is used
- **WHEN** `replan_required` is `auto` with `unscoped: {disposition: notify_with_timeout, timeout_seconds: 600, default_action: block}` and no reference is present
- **THEN** the approval gate SHALL file an approval and apply `block` on timeout

#### Scenario: A reference not from the launch marker is ignored
- **WHEN** the evaluation context carries `roadmap_approval_ref: gate-decision:Z` but `marker_reader` returns None
- **THEN** the unscoped fallback SHALL apply and the record's `scope` SHALL be `unscoped`

#### Scenario: Invalid unscoped config is rejected
- **WHEN** `TRUST_POSTURE.md` declares `unscoped: {disposition: auto}` or declares `unscoped` on `merge`
- **THEN** `validate_posture_file` SHALL return an error naming the gate and field

#### Scenario: Digest ignores prose and key order
- **WHEN** two posture files differ only in Markdown body text and front-matter key order
- **THEN** `posture_digest` SHALL return the same value for both

