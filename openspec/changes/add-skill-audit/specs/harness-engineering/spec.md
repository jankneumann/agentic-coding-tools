# harness-engineering — delta for add-skill-audit

Adds a consumer of the capability-gap tag schema that joins each
`affected_skill:` signal to the dispatch tier that ran the failing phase, so
skill failures can be read per tier rather than only per skill.

## ADDED Requirements

### Requirement: Capability Gap Signals Joined to Dispatch Tier

The `skill-audit` skill SHALL query episodic memory for entries carrying
`affected_skill:<name>` within `--evidence-window` days, across all four
`source` values, using the query and tag-extraction helpers in
`skills/improve-harness/scripts/analyze_failures.py` rather than restating the
tag schema. For each entry it SHALL determine the archetype that ran the
failing phase by, in order: (1) the `phase_archetype` of a `loop-state.json`
whose `change_id` matches the entry's details or handoff, taking the
`phase_history` entry nearest the memory `created_at`; (2) the
`phase_archetype` of the coordinator `GET /discovery/agents` session with the
same `agent_id` whose heartbeat window contains `created_at`; (3) otherwise
the bucket `unknown`. The archetype SHALL then be resolved to
`(provider, model, thinking)` through `model_aliases` for the provider named
in the entry's `agent_type`, or `unknown` when absent. Entries SHALL never be
dropped for lack of a tier. Deduplication SHALL reuse the
`(capability_gap, affected_skill, session_id)` key and SHALL preserve the set
of sources per finding.

The join output SHALL be a table with one row per
`(affected_skill, archetype, provider, model, thinking)` and columns for
count, distinct sessions, max severity, sources, and the fraction of rows
surfaced by two or more sources. A `tier_concentrated_failure` finding SHALL be
emitted when one tier holds at least 60 percent of a skill's failures and at
least three distinct sessions, naming the tier and the count.

#### Scenario: Failure attributed through loop-state

- **WHEN** a memory entry tagged `affected_skill:implement-feature` names a
  `change_id` whose `loop-state.json` records `phase_archetype: implementer`
- **THEN** the join row SHALL carry `archetype: implementer`
- **AND** `model` and `thinking` SHALL equal the `standard` tier entry for the
  entry's provider

#### Scenario: Failure attributed through discovery heartbeat

- **WHEN** no `loop-state.json` matches but `GET /discovery/agents` returns a
  session for the same `agent_id` with `phase_archetype: reviewer` whose
  heartbeat window contains the entry's `created_at`
- **THEN** the join row SHALL carry `archetype: reviewer`

#### Scenario: Unattributable failure is kept

- **WHEN** neither source yields an archetype
- **THEN** the join row SHALL carry `archetype: unknown`
- **AND** the entry SHALL still count toward the skill's total

#### Scenario: Concentrated failure produces a finding

- **WHEN** five of seven failures for `validate-feature` across four sessions
  resolve to `(claude_code, haiku, null)`
- **THEN** a `tier_concentrated_failure` finding SHALL be emitted naming that
  tier and the count `5/7`

#### Scenario: Sources are preserved through the join

- **WHEN** the same gap is surfaced by `session-log` and `transcript-mined`
- **THEN** the join row's `sources` SHALL contain both
- **AND** the report's cross-source agreement line SHALL count it once
