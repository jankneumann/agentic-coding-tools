# skill-workflow — delta for add-skill-audit

Adds a user-invocable `skill-audit` skill that classifies a SKILL.md by layer,
profiles which dispatch tiers run it, joins capability-gap evidence to those
tiers, and emits a findings ledger, a stamped report, and candidate-work stubs.
It is read-only over the audited skill.

## ADDED Requirements

### Requirement: Skill Audit Skill

The system SHALL provide a user-invocable skill `skill-audit` whose entry point
`skills/skill-audit/scripts/skill_audit.py` accepts either one skill name or
`--all`, plus the optional flags `--evidence-window <days>` (default `30`),
`--convention rightsizing|current` (default `rightsizing`), `--propose`,
`--check-freshness`, and `--output-dir <path>` (default
`docs/reports/skill-audit/`). The skill SHALL NOT modify any file under the
audited skill's directory or its runtime mirrors; its only writes SHALL be the
report, the findings ledger, and candidate-work stubs under `--output-dir`.

For each audited skill the entry point SHALL produce, in this order:

1. A **layer classification** that assigns every section of `SKILL.md` and of
   each file one level below `references/` exactly one label from
   `contract | constraint | procedure | teaching | unclassified`. A
   deterministic pre-pass SHALL assign `contract` to frontmatter, fenced
   command blocks, exit-code tables, schema and file-path tables, and any
   paragraph containing a `<skill-base-dir>` invocation; `constraint` to a
   paragraph whose sentences contain a prohibition (`never`, `must not`,
   `SHALL NOT`, `do not`) followed by a stated reason (`because`, `so that`,
   `otherwise`, or a parenthetical rationale); and `procedure` to ordered
   lists whose items begin with an imperative verb. Sections the pre-pass
   cannot decide SHALL be batched into at most one model call per skill,
   dispatched at the `analyst` archetype resolved through the coordinator
   bridge (or omitted when resolution fails), with a strict output schema;
   a response that fails the schema SHALL be logged as a warning and every
   section in that batch SHALL be labelled `unclassified`.
2. A **dispatch profile** listing the archetypes that run the skill, derived
   from `phase_mapping` in `agent-coordinator/archetypes.yaml` for lifecycle
   skills and from the skill's own documented dispatch calls otherwise, and
   for each archetype the `(provider, model, thinking)` tuple per provider as
   resolved by `skills/shared/archetype_roster.py`. Providers SHALL be
   enumerated from the roster file, never from a literal list.
3. A **findings ledger** written as `<skill>-findings.json`, valid against
   `skill-audit-findings.schema.json`, where each finding carries `kind` from
   `teaching_inferable | procedure_without_probe | constraint_without_reason |
   contract_unpinned | missing_deviation_protocol | tier_concentrated_failure |
   convention_drift`, the `layer` and `section` it applies to, an `evidence`
   object, and exactly one `remediation` from
   `keep | move_to_reference | extract_to_script | add_probe | add_reason | delete`.
4. A **markdown report** `<skill>-<date>.md` containing the layer histogram,
   the dispatch profile, the tier failure table from the evidence join, the
   ranked findings, a proposed lean `SKILL.md` outline, a proposed
   `references/procedure.md` outline, and a freshness stamp with
   `archetypes_sha256`, `reviewed_dates`, `evidence_window_days`, and
   `generated_at`.

#### Scenario: Shaped sections are classified without a model call

- **WHEN** `skill_audit.py quick-task` runs with the model backend stubbed to
  fail on any call and every section of `quick-task/SKILL.md` is decidable by
  the pre-pass
- **THEN** the findings ledger SHALL be written with zero `unclassified`
  sections
- **AND** the stub SHALL record zero calls
- **AND** the exit code SHALL be `0`

#### Scenario: Undecidable prose is batched into one model call

- **WHEN** a fixture SKILL.md contains four prose sections the pre-pass cannot
  decide
- **THEN** the classifier SHALL make exactly one model call carrying all four
  sections
- **AND** the call SHALL use the model resolved for the `analyst` archetype,
  or omit the model when resolution fails

#### Scenario: Invalid model output never becomes a label

- **WHEN** the model backend returns output that fails the classification
  schema
- **THEN** every section in that batch SHALL be labelled `unclassified`
- **AND** a warning naming the skill and the batch size SHALL be logged
- **AND** no finding SHALL cite an `unclassified` section as `teaching`

#### Scenario: Dispatch profile follows the roster

- **WHEN** `skill_audit.py autopilot` runs against an `archetypes.yaml` whose
  `model_aliases` contains both bare tier ids and `{model, thinking}` entries
  and omits `frontier` for one provider
- **THEN** the dispatch profile SHALL list every provider present in the file
- **AND** each `(provider, model, thinking)` tuple SHALL equal the value
  `archetype_roster.resolve_tier_for_provider` returns for that archetype's tier
- **AND** the provider lacking `frontier` SHALL show its `premium` model with
  a `degraded_from: frontier` note

#### Scenario: Classification is deterministic

- **WHEN** the same SKILL.md is audited twice with the model backend replaced
  by a fixed stub
- **THEN** the two `<skill>-findings.json` files SHALL be byte-identical

### Requirement: Skill Audit Remediation Safety

The findings schema SHALL declare, and the classifier SHALL enforce, that a
finding whose `layer` is `contract` never carries `remediation: delete`. A
finding of kind `teaching_inferable` SHALL carry `move_to_reference` or
`delete` only when the section cites no repository-specific path, command, or
decision; otherwise the finding SHALL be downgraded to `keep` with the citing
token recorded in `evidence.repo_specific_tokens`.

#### Scenario: Contract sections cannot be deleted

- **WHEN** a findings ledger is constructed with a `contract` finding whose
  remediation is `delete`
- **THEN** schema validation SHALL fail
- **AND** the classifier's guard SHALL raise before writing the ledger

#### Scenario: Teaching that cites repo specifics is kept

- **WHEN** a section explains red-green-refactor and also names
  `docs/decisions/` as where to record the outcome
- **THEN** the finding SHALL have `remediation: keep`
- **AND** `evidence.repo_specific_tokens` SHALL contain `docs/decisions/`

### Requirement: Skill Audit Freshness and Hand-off

The report SHALL carry a freshness stamp, and `--check-freshness` SHALL exit
`1` when the current `archetypes.yaml` content hash differs from the
`archetypes_sha256` in the newest report for that skill (or when no report
exists), and `0` otherwise, printing the two hashes and the `reviewed_dates`
delta. `--propose` SHALL write one candidate-work stub per finding whose
`remediation` is not `keep`, valid against
`openspec/schemas/candidate-work.schema.json`, with `provenance` naming the
report path and the finding id, and `suggested_change_id` of the form
`rightsize-<skill>-<kind>`. Stubs SHALL be written through the same projection
helper `/improve-harness` uses so both skills emit one shape.

#### Scenario: Roster rotation makes the audit stale

- **WHEN** a report exists for `merge-pull-requests` and `archetypes.yaml`
  is then edited so its content hash changes
- **THEN** `skill_audit.py merge-pull-requests --check-freshness` SHALL exit `1`
- **AND** stdout SHALL name both hashes and any changed `reviewed` dates

#### Scenario: Fresh audit passes the check

- **WHEN** a report exists whose `archetypes_sha256` equals the current file
  hash
- **THEN** `--check-freshness` SHALL exit `0`

#### Scenario: Candidate-work stubs are schema-valid and deduplicated

- **WHEN** `skill_audit.py validate-feature --propose` runs against a ledger
  with three non-`keep` findings, two of which share `kind` and `section`
- **THEN** exactly two stubs SHALL be written
- **AND** each SHALL validate against `candidate-work.schema.json`
- **AND** each `provenance` SHALL name the report path and a finding id

### Requirement: Skill Audit Convention Selection

The audit SHALL lint frontmatter, tail block, and layout against the
convention named by `--convention`. `rightsizing` (the default) SHALL treat
`triggers:` as absent-by-design, the tail block as optional, `SKILL.md` over
500 lines as a `convention_drift` finding, and any reference nested more than
one level below `references/` as a `convention_drift` finding. `current` SHALL
apply the assertions in `skills/tests/_shared/skill_invariants.py` unchanged.
The report SHALL state which convention was applied.

#### Scenario: Default convention is rightsizing

- **WHEN** `skill_audit.py <skill>` runs without `--convention`
- **THEN** the report header SHALL read `convention: rightsizing`
- **AND** a SKILL.md lacking `triggers:` SHALL produce no `convention_drift`
  finding for that key

#### Scenario: Current convention flags a missing tail block

- **WHEN** `skill_audit.py <skill> --convention current` runs against a
  `user_invocable: true` SKILL.md with no `## Common Rationalizations` section
- **THEN** a `convention_drift` finding SHALL name `assert_tail_block_present`

### Requirement: Skill Audit Degrades Without the Coordinator

When the coordinator is unreachable, or `try_recall` reports `unauthorized`,
the audit SHALL still complete classification, dispatch profile, findings,
and report, SHALL exit `0`, and SHALL record
`evidence: unavailable (<reason>)` in the report and
`evidence.status: unavailable` in the ledger.

#### Scenario: Coordinator down

- **WHEN** `COORDINATOR_URL` points at a closed port and `skill_audit.py
  plan-feature` runs
- **THEN** the exit code SHALL be `0`
- **AND** the report SHALL contain `evidence: unavailable`
- **AND** the tier failure table SHALL be present with zero rows

### Requirement: Skill Audit Skill Packaging

`skills/skill-audit/SKILL.md` SHALL be at most 150 lines, SHALL reference
files at most one level below `references/`, SHALL declare
`user_invocable: true` and `related: [improve-harness, agent-ergonomics,
prioritize-proposals]`, and SHALL pass its `test_skill_md.py` both with and
without a `triggers:` key. The skill SHALL be registered in
`skills/install-manifest.json` with `cross_skill_dependencies` naming
`shared`, `coordination-bridge`, and `improve-harness`, and
`skills/tests/skill-audit` SHALL appear in the `testpaths` of
`skills/pyproject.toml`.

#### Scenario: Skill test passes in both frontmatter states

- **WHEN** `test_skill_md.py` runs against `SKILL.md` with `triggers:` present
  and again with it removed
- **THEN** both runs SHALL pass

#### Scenario: Install manifest and testpaths include the skill

- **WHEN** `bash skills/install.sh --check` and the CI coverage test run
- **THEN** both SHALL pass with `skill-audit` present
