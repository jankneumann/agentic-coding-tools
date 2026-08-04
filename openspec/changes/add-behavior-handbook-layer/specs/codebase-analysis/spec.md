# codebase-analysis — Delta: add-behavior-handbook-layer

## ADDED Requirements

### Requirement: Behavior Handbook Artifact Schema

The system SHALL produce a behavior handbook artifact `architecture.behaviors.json` organized as a three-level behavior-centric representation layered on top of the canonical architecture graph.

- Level 1 (`system_flows[]`) SHALL describe end-to-end request flows: entry, ordered stages, state handoffs between stages, and terminal actions
- Level 2 (`behavior_units[]`) SHALL describe named behavior units with `id` (stable, format `bh:{kebab-name}`), `title`, `responsibility`, `inputs[]`, `outputs[]`, `depends_on[]` (other behavior unit IDs), and `member_nodes[]` (canonical graph node IDs)
- Level 3 (`unit_details{}`) SHALL, per behavior unit, describe `triggers[]`, `state_changes[]`, `execution_paths[]`, `exception_paths[]`, and `evidence[]`
- Every `member_nodes[]` entry and every `evidence[]` entry SHALL reference node IDs that exist in `architecture.graph.json`; the handbook SHALL NOT define structural facts of its own
- The artifact SHALL carry a `snapshot` block with `generated_at` (ISO 8601, derived from `SOURCE_DATE_EPOCH`), `git_sha`, and `handbook_version`
- The system SHALL provide a schema validation script for `architecture.behaviors.json`

#### Scenario: Validate a well-formed handbook
- **WHEN** `architecture.behaviors.json` contains system flows, behavior units, and unit details conforming to the schema, with all referenced node IDs present in `architecture.graph.json`
- **THEN** the handbook schema validator SHALL report success with no errors

#### Scenario: Reject a handbook referencing unknown graph nodes
- **WHEN** a behavior unit's `member_nodes[]` or an evidence entry references a node ID absent from `architecture.graph.json`
- **THEN** the validator SHALL report a validation error identifying the behavior unit and the dangling node ID
- **AND** the refresh pipeline SHALL NOT promote the staged handbook artifact

### Requirement: Verified Evidence Locators

Every Level 3 evidence entry SHALL carry a verifiable locator binding the claim to source: `node_id`, `file`, `span` (start/end lines), and `content_digest` (SHA-256 of the spanned source at synthesis time), and the system SHALL provide a locator resolver that re-verifies locators against the working tree.

- The resolver SHALL classify each locator as `verified` (digest matches), `drifted` (file and symbol resolve but digest differs), or `unresolvable` (file or symbol missing)
- `drifted` and `unresolvable` locators SHALL be recorded as findings in `architecture.diagnostics.json` with the owning behavior unit ID
- `make architecture-check` SHALL exit non-zero when any locator is `unresolvable`

#### Scenario: All locators verify against HEAD
- **WHEN** the locator resolver runs against a working tree identical to the synthesis revision
- **THEN** every locator SHALL be classified `verified`
- **AND** `architecture.diagnostics.json` SHALL contain no locator findings

#### Scenario: Source drifts under a locator
- **WHEN** a file spanned by an evidence locator is edited so the spanned content digest no longer matches
- **THEN** the resolver SHALL classify that locator `drifted` and record a warning finding naming the behavior unit and file
- **AND** the freshness check SHALL report the handbook stale with a locator-drift reason code

#### Scenario: Evidence target deleted
- **WHEN** a file or symbol referenced by an evidence locator no longer exists
- **THEN** the resolver SHALL classify the locator `unresolvable` and record an error finding
- **AND** `make architecture-check` SHALL exit non-zero

### Requirement: Handbook Provenance and Freshness

The behavior handbook SHALL be covered by the existing content-based provenance and freshness system: `architecture.provenance.json` SHALL record the handbook artifact digest and the input fingerprint of the Layer 1/2 artifacts it was synthesized from.

- Handbook staleness SHALL be content-based: stale only when a relevant input changed, producer identity changed, or the artifact's bytes drifted from the recorded digest — never merely by age
- A failed handbook synthesis SHALL preserve the last known-good committed handbook

#### Scenario: Repeat refresh yields no diff
- **WHEN** `make architecture-refresh` runs twice at the same revision with unchanged inputs and a committed behavior map
- **THEN** the promoted handbook artifacts SHALL be byte-identical across runs
- **AND** the repository SHALL show no diff

#### Scenario: Synthesis failure preserves last known-good
- **WHEN** handbook synthesis fails mid-run (e.g., the structuring step errors)
- **THEN** the previously committed `architecture.behaviors.json` SHALL remain in place unmodified
- **AND** the pipeline SHALL exit non-zero identifying the failed stage

### Requirement: Progressive Disclosure Query Interface

The system SHALL provide a query CLI that serves the handbook one level at a time under explicit token budgets, so consumers load only the levels they need.

- `--level l1` SHALL return the system-flow overview within approximately 400 tokens
- `--level l2 [--unit <id>|--filter <expr>]` SHALL return behavior unit cards of approximately 150 tokens each, filterable by touched files (for reviewers) or free-text behavior query (for planners)
- `--level l3 --unit <id>` SHALL return one unit's full detail within approximately 1500 tokens, and SHALL run locator verification on the returned evidence, marking each entry `verified`/`drifted`/`unresolvable`
- `--locate "<behavior description>"` SHALL return ranked candidate behavior units with their member nodes as source-grounded localization evidence
- Output SHALL be JSON suitable for direct inclusion in an agent context block

#### Scenario: Planner localizes a behavior
- **WHEN** an agent runs the query CLI with `--locate "retry on tool timeout"`
- **THEN** the CLI SHALL return ranked behavior units with member node IDs, files, and spans
- **AND** the response SHALL NOT include Level 3 details of unrelated units

#### Scenario: L3 request against drifted source
- **WHEN** `--level l3 --unit <id>` is requested and one of the unit's locators no longer digest-matches
- **THEN** the CLI SHALL still return the unit detail
- **AND** the affected evidence entry SHALL be marked `drifted` so the consumer treats it as unverified

### Requirement: Handbook HTML Drill-Down View

The system SHALL generate a self-contained HTML artifact rendering the handbook as a progressive drill-down (L1 flow → L2 unit cards → L3 detail panes) with persona-selectable entry presets.

- The page SHALL be a single file with no external network dependencies
- Persona presets SHALL configure entry level and traversal order: newcomer (L1, breadth-first), reviewer (L2 filtered by a supplied file list), planner (behavior search), auditor (L3 exception paths)
- Each L3 evidence entry SHALL render its `file:span` locator and its verification status from the most recent resolver run

#### Scenario: Generate and open the drill-down
- **WHEN** the HTML generator runs against a valid `architecture.behaviors.json`
- **THEN** it SHALL emit `views/handbook.html` renderable offline
- **AND** selecting a behavior unit card SHALL reveal its L3 detail without loading other units' details

#### Scenario: Generator refuses an invalid handbook
- **WHEN** the HTML generator is run against a handbook artifact that fails schema validation
- **THEN** it SHALL exit non-zero without writing `views/handbook.html`
- **AND** it SHALL print the validation errors

### Requirement: Behavior Seeding From Existing Artifacts

Handbook synthesis SHALL seed behavior unit discovery from existing pipeline outputs rather than raw source alone: `entrypoints[]` from the canonical graph, `high_impact_nodes`, disconnected endpoints, and exception patterns from `treesitter_enrichment.json`.

- Every entrypoint in the canonical graph SHALL be reachable from at least one behavior unit, or SHALL be listed in a handbook `uncovered[]` section with a reason
- Exception patterns SHALL be promoted into the owning unit's `exception_paths[]` rather than remaining only aggregate statistics

#### Scenario: Disconnected endpoint gains a behavior home
- **WHEN** synthesis runs against a graph containing endpoints with no traced downstream flow
- **THEN** each such endpoint SHALL appear either in a behavior unit's `member_nodes[]` or in `uncovered[]` with a reason
- **AND** the count of uncovered entrypoints SHALL be reported in the synthesis summary

#### Scenario: Exception handling surfaces as an exception path
- **WHEN** `treesitter_enrichment.json` records an exception-handling pattern within a behavior unit's member nodes
- **THEN** the unit's L3 `exception_paths[]` SHALL include a corresponding entry with an evidence locator
