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
- **AND** every projected opportunity SHALL provide a stable opportunity ID
- **AND** already-scaffolded opportunities SHALL NOT create duplicate candidate work
- **AND** hinted or derived IDs SHALL be normalized to the canonical change-ID prefixes
- **AND** only blockers resolving to exact change IDs SHALL populate `depends_on`
- **AND** prose blockers SHALL remain inert rationale or tags

#### Scenario: Producers assign comparable priority

- **WHEN** supported generators project entries into a mixed candidate batch
- **THEN** each adapter SHALL map source evidence onto the shared five-band priority scale
- **AND** source-local rank SHALL NOT be treated as an unbounded cross-generator priority
- **AND** explore-feature SHALL apply its documented 1.0..3.3 weighted-score formula (`focus_match` 0 through 3) and fixed bands rather than mapping shortlist position
- **AND** explore-feature SHALL NOT emit priority 1 because its source contract has no critical or immediate field

#### Scenario: Producer prefixes are normalized

- **WHEN** bug-scrub or improve-harness receives a `fix-` or unprefixed suggested ID
- **THEN** the adapter SHALL normalize it to the canonical `update-` prefix
- **AND** an already canonical add/update/remove/refactor prefix SHALL remain unchanged

#### Scenario: Derived candidate identity is stable

- **WHEN** the same producer source is projected after line, title, report path, collector order/rank, or non-identity provenance changes
- **THEN** its derived suggested ID SHALL remain unchanged
- **AND** the identity object SHALL contain exactly `generator` and `source_id`
- **AND** bug-scrub SHALL use `bug-finding-<semantic-hash>`, improve-harness SHALL use the trimmed, whitespace-collapsed, lowercase capability gap, and explore-feature SHALL use the exact stable opportunity ID
- **AND** bug-scrub base semantic JSON SHALL contain exactly `source`, `source_key`, `category`, `file_path`, `detail`, `origin_change_id`, and `origin_artifact_path`, with one-based `occurrence` as the exact eighth final fingerprint field
- **AND** paths SHALL only slash-normalize while preserving whitespace
- **AND** detail SHALL strip only an exact leading full `<file_path>:<numeric-line>:` prefix independent of line metadata, SHALL NOT strip a basename-only prefix, and SHALL then whitespace-collapse
- **AND** bug-scrub `source_key` SHALL retain stable pytest/security/other collector keys while stripping known volatile ruff/mypy/marker line suffixes, architecture/deferred ordinals, and OpenSpec ordinals already represented by semantic detail/path
- **AND** equal base identities SHALL receive deterministic occurrence ordinals after sorting by line and the documented stable fallbacks, so repeated equivalent findings remain distinct while singleton line shifts and global collector reorder remain stable
- **AND** bug-scrub SHALL exclude the unmodified finding ID, line, age, origin line/task/index, severity, title, report path, and collector order/rank from base semantic identity while retaining the original finding ID in provenance
- **AND** `semantic-hash` SHALL be the first 16 lowercase SHA-256 hex characters of final canonical JSON, and distinct final fingerprints that collide on the compact source ID MUST fail the complete batch
- **AND** the readable base SHALL derive only from `source_id` by the documented ASCII slug algorithm and `item` fallback
- **AND** canonical serialization SHALL use sorted keys, compact comma/colon separators, unescaped Unicode, and UTF-8 before SHA-256
- **AND** explicit source hints SHALL remain normalized but unsuffixed
- **AND** duplicate final IDs MUST fail the whole batch before replacement

#### Scenario: Bug-scrub mappings reject unknown labels

- **WHEN** bug-scrub projects findings from its supported categories and severities
- **THEN** effort SHALL follow the exhaustive category-only mapping
- **AND** severity SHALL be trimmed, lowercased, and mapped through the critical/high/medium/low/info priority vocabulary
- **AND** an unknown category or severity MUST fail the complete sidecar with a concise validation error before replacement

#### Scenario: Improve-harness effort is independent of urgency

- **WHEN** improve-harness projects gaps with equal `max_severity` but different affected-skill counts
- **THEN** priority SHALL remain equal while effort SHALL follow the documented affected-skill bands
- **AND** missing affected-skill evidence SHALL map to M with an `effort-estimate-default` tag
- **AND** `max_severity` SHALL be trimmed, lowercased, and mapped through the critical/high/medium/low vocabulary
- **AND** an unknown `max_severity` MUST fail with a concise validation error before candidate-sidecar replacement

#### Scenario: Explicit sidecar destination collides

- **WHEN** a producer targets an existing valid non-empty candidate batch owned by another generator
- **THEN** it MUST refuse replacement and identify the generator collision
- **AND** the existing destination bytes SHALL remain unchanged

#### Scenario: Candidate batch validation fails

- **WHEN** any projected candidate violates the canonical schema
- **THEN** the generator MUST fail with a field-level error
- **AND** it MUST NOT replace the destination with a partial batch

#### Scenario: Candidate sidecar is deterministic and complete

- **WHEN** the same input and repository state are processed twice
- **THEN** complete sidecar bytes SHALL be identical
- **AND** every stub SHALL retain generator and source provenance

#### Scenario: Candidate text is rendered safely

- **WHEN** candidate ranking renders title, rationale, tags, or provenance
- **THEN** source text SHALL be escaped as inert Markdown or terminal text
- **AND** provenance URIs SHALL NOT be dereferenced, fetched, or executed

#### Scenario: Requested candidate discovery returns no eligible entries

- **WHEN** a generator with a file-backed or explicitly requested candidate destination succeeds with no eligible entries
- **THEN** it SHALL atomically persist an empty candidate array
- **AND** stale candidates SHALL NOT remain
- **AND** improve-harness stdout-only mode without an explicit candidate destination SHALL remain write-free

### Requirement: Prioritize-proposals ranks mixed candidate work

`/prioritize-proposals` SHALL accept one or more candidate-work objects or arrays through
a repeatable `--candidate-work PATH` option and rank candidate stubs from all supported generators with deterministic tie-breakers.

#### Scenario: Mixed producer batch is ranked

- **WHEN** three supplied sidecars contain valid stubs from bug-scrub, improve-harness, and explore-feature
- **THEN** the loader SHALL validate each file, concatenate them in argument order, and reject duplicate final IDs across the union
- **AND** the prioritization output SHALL include every stub exactly once
- **AND** each entry SHALL retain its generator and provenance
- **AND** repeated ranking of identical input SHALL produce the same order
- **AND** a missing optional provenance generator SHALL use the empty-string tie-break key

#### Scenario: Mixed batch contains a malformed stub

- **WHEN** any member of the candidate batch is malformed
- **THEN** prioritization MUST refuse the entire batch before scoring
- **AND** the error SHALL identify the offending batch index and field

#### Scenario: Mixed batch contains dependencies

- **WHEN** valid candidates contain an acyclic dependency edge and stable-key ties
- **THEN** the dependency SHALL precede its dependent
- **AND** deterministic tie-breakers SHALL produce a stable order
- **AND** candidate entries SHALL remain distinct from proposal entries
- **AND** the shared resolver SHALL collapse duplicate completed/archive lifecycle records and preserve one unique live match
- **AND** an active-incomplete or unknown external dependency SHALL mark its candidate and all transitive in-batch dependents blocked
- **AND** ready components SHALL precede blocked components without violating dependency order

#### Scenario: Mixed batch has a cycle or duplicate change ID

- **WHEN** candidates form a cycle, repeat a suggested change ID, or a dependency has multiple live matches
- **THEN** prioritization MUST refuse the lane before scoring
- **AND** the error SHALL name the conflicting candidates
