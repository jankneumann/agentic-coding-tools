## ADDED Requirements

### Requirement: Discovery generators emit canonical candidate work

Bug-scrub, improve-harness, and explore-feature MUST be capable of emitting
candidate-work stubs that conform to `openspec/schemas/candidate-work.schema.json`
while preserving their existing rich artifacts.

#### Scenario: Bug-scrub promotes a finding

- **WHEN** an eligible bug-scrub finding is promoted to candidate work
- **THEN** the emitted stub SHALL validate against the canonical schema
- **AND** provenance SHALL identify the bug-scrub report and finding ID
- **AND** the existing bug-scrub report SHALL remain unchanged

#### Scenario: Improve-harness emits a capability-gap candidate

- **WHEN** improve-harness emits candidate work for a ranked capability gap
- **THEN** the emitted stub SHALL validate against the canonical schema
- **AND** provenance SHALL identify the report and source entry IDs
- **AND** the legacy markdown proposal-stub path SHALL remain available during the migration window

#### Scenario: Explore-feature emits shortlist candidates

- **WHEN** explore-feature persists a ranked shortlist
- **THEN** every eligible untracked opportunity SHALL have a schema-valid candidate-work projection
- **AND** the rich HMW, lens, and rejected-alternative data SHALL remain in `opportunities.json`
- **AND** already-scaffolded opportunities SHALL NOT create duplicate candidate work
- **AND** hinted or derived IDs SHALL be normalized to the canonical change-ID prefixes
- **AND** only blockers resolving to exact change IDs SHALL populate `depends_on`
- **AND** prose blockers SHALL remain inert rationale or tags

#### Scenario: Producers assign comparable priority

- **WHEN** supported generators project entries into a mixed candidate batch
- **THEN** each adapter SHALL map source evidence onto the shared five-band priority scale
- **AND** source-local rank SHALL NOT be treated as an unbounded cross-generator priority

#### Scenario: Candidate batch validation fails

- **WHEN** any projected candidate violates the canonical schema
- **THEN** the generator MUST fail with a field-level error
- **AND** it MUST NOT replace the destination with a partial batch

#### Scenario: Candidate sidecar is deterministic and complete

- **WHEN** the same input and repository state are processed twice
- **THEN** complete sidecar bytes SHALL be identical
- **AND** every stub SHALL retain generator and source provenance

#### Scenario: Candidate text is rendered safely

- **WHEN** a report renders candidate title, rationale, tags, or provenance
- **THEN** source text SHALL be escaped as inert Markdown or terminal text
- **AND** provenance URIs SHALL NOT be dereferenced, fetched, or executed

#### Scenario: Discovery returns no eligible entries

- **WHEN** a generator succeeds with no eligible entries
- **THEN** it SHALL atomically persist an empty candidate array
- **AND** stale candidates SHALL NOT remain

### Requirement: Prioritize-proposals ranks mixed candidate work

`/prioritize-proposals` SHALL accept a validated candidate-work object or array and
rank candidate stubs from all supported generators with deterministic tie-breakers.

#### Scenario: Mixed producer batch is ranked

- **WHEN** a batch contains valid stubs from bug-scrub, improve-harness, and explore-feature
- **THEN** the prioritization output SHALL include every stub exactly once
- **AND** each entry SHALL retain its generator and provenance
- **AND** repeated ranking of identical input SHALL produce the same order

#### Scenario: Mixed batch contains a malformed stub

- **WHEN** any member of the candidate batch is malformed
- **THEN** prioritization MUST refuse the entire batch before scoring
- **AND** the error SHALL identify the offending batch index and field

#### Scenario: Mixed batch contains dependencies

- **WHEN** valid candidates contain an acyclic dependency edge and stable-key ties
- **THEN** the dependency SHALL precede its dependent
- **AND** deterministic tie-breakers SHALL produce a stable order
- **AND** candidate entries SHALL remain distinct from proposal entries

#### Scenario: Mixed batch has a cycle or duplicate change ID

- **WHEN** candidates form a cycle or repeat a suggested change ID
- **THEN** prioritization MUST refuse the lane before scoring
- **AND** the error SHALL name the conflicting candidates
