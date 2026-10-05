# agent-identity Specification (delta)

Change `ownership-map` extends the principal registry with human principals. Agent identity,
credentials and projections are unchanged; this delta adds one requirement and touches none of
the existing ones.

## ADDED Requirements

### Requirement: Human Principal Registry Extension

`agent-coordinator/agents.yaml` MAY declare a top-level `humans:` mapping of human principals.
Each entry SHALL require `display_name` and MAY declare `github`, `email`, `domains`,
`availability` (`timezone`, `hours`, `days`) and `description`; the schema SHALL reject unknown
fields. Human ids SHALL share the principal namespace with agent names and follow the same slug
pattern; a human id equal to an agent name SHALL be a load error naming both entries.
`load_agents_config()` SHALL continue to return only agents; a separate
`load_human_principals()` SHALL return `HumanEntry` records. Human principals SHALL NOT be
projected into any agent runtime state: no `agent_profiles` row, no `agent_profile_assignments`
row, no API-key identity, no dispatch config and no OpenBao AppRole, policy or data path. The
inline human principal schema in `agents_config.py` SHALL equal
`openspec/schemas/human-principals.schema.json` (ignoring schema metadata keys), and the
Registry Projection Invariant SHALL assert that no human id appears in any projection.

#### Scenario: Human principal declared without agent projection
- **GIVEN** `agents.yaml` declares `humans: {jan: {display_name: "Jan Neumann", github: jankneumann}}`
- **WHEN** `load_agents_config()`, `sync_profiles()`, `get_api_key_identities()`,
  `get_dispatch_configs()` and `project_principals()` run
- **THEN** none of their outputs SHALL contain the id `jan`
- **AND** `load_human_principals()` SHALL return one `HumanEntry` with `name == "jan"`

#### Scenario: Human id colliding with an agent name rejected
- **GIVEN** `agents.yaml` declares agent `claude-local` and human `claude-local`
- **WHEN** `load_agents_config()` runs
- **THEN** it SHALL raise `ValueError` naming `claude-local` as both an agent and a human

#### Scenario: Human entry missing display name rejected
- **WHEN** a `humans:` entry omits `display_name`
- **THEN** schema validation SHALL fail naming the entry and the missing field

#### Scenario: Registry without humans unchanged
- **GIVEN** an `agents.yaml` with no `humans:` block
- **WHEN** `load_agents_config()` and `sync_profiles()` run
- **THEN** their results SHALL be identical to the pre-change behavior
- **AND** `load_human_principals()` SHALL return an empty list

#### Scenario: Schema mirror pinned
- **WHEN** `openspec/schemas/human-principals.schema.json` is loaded and its `$schema`, `$id`,
  `title` and `description` keys are removed
- **THEN** the result SHALL equal `HUMAN_PRINCIPAL_SCHEMA` in `agents_config.py`

#### Scenario: Invariant catches a human projected as an agent
- **GIVEN** a synced profile table into which a row named after a declared human is injected
- **WHEN** the registry projection invariant checkers run
- **THEN** the human-projection checker SHALL report a violation naming that id
