## ADDED Requirements

### Requirement: Versioned evidence ledger schema

The system SHALL provide a JSON Schema (Draft 2020-12) named `evidence-ledger.schema.json`
with `schema_version` 1. The schema SHALL define:
- **facts**: `id`, `kind`, `source`, `gathered_by`, `host`, `time_window`, `tool_version`,
  `role` (one of `variable` or `control`), and `observation`;
- **signals**: `id`, `variable_fact`, `control_fact`, and `classification` (one of `signal`
  or `noise`);
- **hypotheses**: `id`, `statement`, `cites`, optional `components`, and `status` (one of
  `open`, `supported`, `rejected` or `root_cause`);
- **reverify_requests**: `id`, `fact_id`, `reason`, `requested_by`, and optional
  `replacement_fact`.

Every object in the schema MUST reject unknown properties.

#### Scenario: Fixture ledger with variable and control facts, a signal and a cited hypothesis validates

- **WHEN** the validator is run on a fixture ledger that contains:
  - a variable fact;
  - a control fact;
  - a signal that derives from the two;
  - a hypothesis that cites both facts;
- **THEN** it reports no violations
- **AND** the CLI exits with code 0

#### Scenario: Fact missing a provenance field is rejected

- **WHEN** a fixture ledger contains a fact without `tool_version`
- **THEN** the validator reports a `schema_violation` whose path names that fact

#### Scenario: Unknown property is rejected

- **WHEN** a fixture ledger contains a fact with a property that the schema does not define
- **THEN** the validator reports a `schema_violation`

#### Scenario: Schema copies stay identical

- **WHEN** the drift test compares the following copies:
  - the canonical `openspec/schemas/evidence-ledger.schema.json`;
  - the skill's `install_assets` copy;
  - the change-local draft, located through `change_dir()`;
- **THEN** all three copies are byte-identical

### Requirement: Signals pair exactly one variable fact with one control fact

Each signal SHALL reference exactly one variable fact and exactly one control fact. The
reference SHALL be a single fact id, not a list, and each signal SHALL carry a
`classification` of `signal` or `noise`.

The validator MUST reject a signal in any of these cases:
- its `variable_fact` does not resolve to a fact whose role is `variable`;
- its `control_fact` does not resolve to a fact whose role is `control`;
- both references name the same fact.

#### Scenario: Signal referencing two variable facts is rejected

- **WHEN** a signal's `control_fact` names a fact whose role is `variable`
- **THEN** the validator reports `signal_role_mismatch`

#### Scenario: Signal referencing a list of facts is rejected

- **WHEN** a signal's `variable_fact` is an array of fact ids
- **THEN** the validator reports a `schema_violation`

#### Scenario: Signal with an unknown classification is rejected

- **WHEN** a signal's `classification` is `maybe`
- **THEN** the validator reports a `schema_violation`

#### Scenario: Signal referencing a missing fact is rejected

- **WHEN** a signal's `variable_fact` names an id that is not a recorded fact
- **THEN** the validator reports `unknown_fact_ref`

### Requirement: Ledger referential integrity

The validator SHALL enforce all of the following:
- ids are unique across all collections in a ledger;
- every hypothesis citation resolves to a recorded fact;
- every hypothesis component resolves to another, non-composite hypothesis in the same
  ledger;
- every reverify request targets a recorded fact;
- a reverify request's replacement fact is a different recorded fact from the one it
  targets;
- every `time_window` has parseable ISO-8601 timestamps, and `start` is not after `end`.

#### Scenario: Hypothesis citing an unknown fact is rejected

- **WHEN** a hypothesis cites a fact id that is not in the ledger
- **THEN** the validator reports `unknown_fact_ref`

#### Scenario: Duplicate id across collections is rejected

- **WHEN** a hypothesis has the same id as a fact
- **THEN** the validator reports `duplicate_id`

#### Scenario: Self-referencing component is rejected

- **WHEN** a hypothesis lists its own id in `components`
- **THEN** the validator reports `self_component`

#### Scenario: Inverted time window is rejected

- **WHEN** a fact's `time_window.start` is later than its `time_window.end`
- **THEN** the validator reports `time_window_inverted`

#### Scenario: Reverify request naming the disputed fact as its own replacement is rejected

- **WHEN** a reverify request's `replacement_fact` equals its `fact_id`
- **THEN** the validator reports `replacement_is_target`

### Requirement: Recorded facts are immutable across ledger revisions

Given a previous and a current revision of the same ledger, the validator SHALL reject the
current revision in any of these cases:
- a fact id from the previous revision is absent;
- a fact's content differs from the previous revision in any field;
- a reverify request from the previous revision is absent or changed;
- the `ledger_id` differs.

The validator SHALL accept a revision that appends new facts and new reverify requests while
it leaves every previously recorded fact and reverify request unchanged. Signals and
hypotheses MAY change between revisions.

#### Scenario: In-place edit of a recorded fact is rejected

- **WHEN** the current revision changes the `observation` of a fact that was recorded in the
  previous revision
- **THEN** `check_revision` reports `fact_mutated` for that fact id
- **AND** the CLI run with `--previous` exits with code 1

#### Scenario: Same dispute expressed as reverify request plus new fact is accepted

- **WHEN** the current revision does all of the following:
  - keeps the disputed fact unchanged;
  - adds a new fact carrying the re-gathered observation;
  - adds a `reverify_request` whose `fact_id` is the disputed fact and whose
    `replacement_fact` is the new fact;
- **THEN** both validation and `check_revision` report no violations

#### Scenario: Removing a recorded fact is rejected

- **WHEN** the current revision omits a fact id that was present in the previous revision
- **THEN** `check_revision` reports `fact_removed`

#### Scenario: Editing a recorded reverify request is rejected

- **WHEN** the current revision changes the `reason` of a reverify request that was recorded
  in the previous revision
- **THEN** `check_revision` reports `reverify_mutated`

#### Scenario: Hypothesis status change is accepted

- **WHEN** the only difference between the revisions is a hypothesis status that moves from
  `open` to `rejected`
- **THEN** `check_revision` reports no violations

### Requirement: Deterministic validator interface

The validator SHALL be importable as the module `evidence_ledger`. It SHALL expose
`load_ledger`, `validate_ledger` and `check_revision`, and it SHALL load ledgers from either
YAML or JSON.

Its CLI `validate <ledger> [--previous <ledger>] [--json]` MUST exit with:
- 0 when there are no violations;
- 1 when there are violations;
- 2 on a usage or load error.

Given the same inputs, the CLI MUST produce the same violation list in the same order.

#### Scenario: YAML ledger validates identically to JSON

- **WHEN** the same ledger content is validated once from a `.yaml` file and once from a
  `.json` file
- **THEN** both runs report identical violation lists

#### Scenario: Unquoted YAML timestamps stay strings

- **WHEN** a YAML ledger writes `time_window.start` as an unquoted ISO-8601 timestamp
- **THEN** the loader returns it as a string
- **AND** the ledger validates without a `schema_violation`

#### Scenario: Unreadable ledger exits with code 2

- **WHEN** the CLI is pointed at a path that does not exist
- **THEN** it exits with code 2

### Requirement: Validator tests resolve OpenSpec paths through change_dir

The validator tests SHALL live under `skills/tests/evidence-ledger/`, and they SHALL be
collected by the shared `skills/pyproject.toml` `testpaths`. Any test that reads a file under
an OpenSpec change directory MUST locate that directory with `change_dir()`, and MUST NOT
pin a literal `openspec/changes/<change-id>/` path.

#### Scenario: Drift test survives archival

- **WHEN** the change directory moves to `openspec/changes/archive/<date>-<id>/`
- **THEN** the drift test still locates the change-local schema draft through `change_dir()`
