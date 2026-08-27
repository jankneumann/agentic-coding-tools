# skill-workflow Delta

## MODIFIED Requirements

### Requirement: Review Findings Schema Extension

The schema at `openspec/schemas/review-findings.schema.json` (mirrored at
`skills/parallel-infrastructure/install_assets/openspec/schemas/review-findings.schema.json`
and inlined in `agent-coordinator/agents.yaml`) SHALL encode an 8-axis review
categorization and the 5 severity prefixes.

The schema SHALL define:

- An `axis` field on each finding with enum values: `correctness`, `readability`,
  `architecture`, `security`, `performance`, `observability`, `resilience`,
  `compatibility`
- A `severity` field on each finding with enum values: `critical`, `nit`, `optional`,
  `fyi`, `none`

Both fields SHALL be required for new findings. Findings produced before this change
SHALL be migratable by setting `axis: "correctness"` and `severity: "fyi"` as defaults.
All copies of the schema (canonical, install-assets mirror, `agents.yaml` inline) SHALL
carry the identical enum.

#### Scenario: New finding includes axis and severity

**WHEN** a parallel-review skill produces a finding
**THEN** the finding JSON SHALL include both `axis` and `severity` fields
**AND** the values SHALL match the schema enums

#### Scenario: NFR axes accepted by the schema

**WHEN** a finding with `axis` set to `observability`, `resilience`, or `compatibility`
is validated against the schema
**THEN** validation SHALL pass

#### Scenario: Schema validation rejects missing fields

**WHEN** a finding without `axis` or `severity` is validated against the updated schema
**THEN** validation SHALL fail with a clear error identifying the missing field

#### Scenario: Existing schema fields preserved

**WHEN** the updated schema is loaded
**THEN** all pre-existing required fields SHALL remain required
**AND** all pre-existing enum values SHALL remain valid

#### Scenario: Schema copies stay identical

**WHEN** the canonical schema, the install-assets mirror, and the `agents.yaml` inline
copy are compared
**THEN** their `axis` and `severity` enums SHALL be identical
