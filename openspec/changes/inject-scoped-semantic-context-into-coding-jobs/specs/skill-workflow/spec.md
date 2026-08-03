## ADDED Requirements

### Requirement: Scoped Semantic Context Retrieval

Context assembly SHALL request semantic code results only for the exact
repository revision the coding job is working against and only within the work
package's declared read scope. The requesting revision SHALL be the full Git
object ID of `HEAD` in the agent's own worktree, and the requested scope SHALL
be derived from the package's resolved `read_allow` and `deny` globs with `deny`
taking precedence.

<!-- Scenario ID: skill-workflow.semantic-context-exact-revision -->
#### Scenario: The exact worktree revision is requested

- **WHEN** a coding job assembles context inside a worktree
- **THEN** the request SHALL carry the full 40-character object ID of that
  worktree's `HEAD`
- **AND** it SHALL NOT substitute the integration branch tip, a merge base, or
  an abbreviated revision

<!-- Scenario ID: skill-workflow.semantic-context-declared-scope -->
#### Scenario: The declared package scope is the requested scope

- **WHEN** the job belongs to a work package
- **THEN** the requested read scope SHALL be that package's resolved
  `read_allow` and `deny` globs
- **AND** a path matching both SHALL be excluded
- **AND** the assembly SHALL NOT widen the scope to the repository root

<!-- Scenario ID: skill-workflow.semantic-context-no-declared-scope -->
#### Scenario: A job with no declared scope does not invent one

- **WHEN** a coding job has no work package and therefore no declared read scope
- **THEN** context assembly SHALL NOT issue a semantic request
- **AND** it SHALL emit an out-of-scope fallback

### Requirement: Bounded Semantic Code Context Section

Context assembly SHALL be able to supply a coding job with a single
`Semantic code context` section, bounded by an explicit budget over hit count,
distinct file count, total rendered lines, and per-hit rendered lines.

<!-- Scenario ID: skill-workflow.semantic-context-consumers -->
#### Scenario: Every named coding job can receive the section

- **WHEN** implementation, quick-task, iteration, debugging, validation, or
  implementation review assembles its context
- **THEN** each of those jobs SHALL be able to receive the
  `Semantic code context` section through one shared retrieval helper
- **AND** each SHALL identify itself with a distinct consumer identifier

<!-- Scenario ID: skill-workflow.semantic-context-single-section -->
#### Scenario: The section appears at most once

- **WHEN** a context block is assembled for one coding job
- **THEN** it SHALL contain at most one `Semantic code context` section

### Requirement: Semantic Hit Provenance

Every injected semantic hit SHALL carry its file path, its start and end line
numbers, its relevance score, the commit the serving index was built from, the
serving index identifier, and its scope decision.

<!-- Scenario ID: skill-workflow.semantic-context-hit-provenance -->
#### Scenario: A rendered hit is fully attributed

- **WHEN** a hit is rendered into the section
- **THEN** it SHALL display the file path, the line range, the score, the
  indexed commit, the index identifier, and the scope decision
- **AND** the machine-readable record SHALL contain the same six values

<!-- Scenario ID: skill-workflow.semantic-context-section-provenance -->
#### Scenario: The section states which index answered

- **WHEN** the section is injected
- **THEN** its header SHALL identify the repository, the requested revision, the
  index namespace, the serving index identifier, and the resolved scope decision

### Requirement: Deterministic Semantic Hit Omission

Duplicate and over-budget hits SHALL be omitted deterministically. Ordering,
deduplication, and budget admission SHALL depend only on the retrieval response
and the configured budget, never on wall-clock time, hash-set iteration order,
process identity, or the order in which the service returned results.

<!-- Scenario ID: skill-workflow.semantic-context-stable-order -->
#### Scenario: Reordered input produces identical output

- **WHEN** the same set of hits is processed twice in different input orders
- **THEN** the retained hits, their sequence, and every omission reason SHALL be
  identical

<!-- Scenario ID: skill-workflow.semantic-context-duplicates -->
#### Scenario: Duplicate hits are omitted with a reason

- **WHEN** two hits share a file path and line range, or one hit's line range is
  contained within a retained hit's range for the same file
- **THEN** exactly one SHALL be retained
- **AND** the omitted hit SHALL be recorded with a duplicate reason

<!-- Scenario ID: skill-workflow.semantic-context-budget -->
#### Scenario: Over-budget hits are omitted with a reason

- **WHEN** admitting a hit would exceed the hit-count, file-count,
  total-line, or per-hit-line bound
- **THEN** that hit SHALL be omitted with the corresponding reason
- **AND** a later hit that still fits SHALL still be admitted
- **AND** omitted hits SHALL NOT be truncated and presented as complete

### Requirement: Explicit Semantic Context Fallback

A stale, unavailable, revision-mismatched, or out-of-scope retrieval outcome
SHALL produce an explicit exact-search fallback instruction and SHALL NOT block
or fail the coding job. Retrieval SHALL never raise to its caller.

<!-- Scenario ID: skill-workflow.semantic-context-fallback-stale -->
#### Scenario: A stale working tree falls back

- **WHEN** the worktree has uncommitted changes, or no index exists for the
  requested revision
- **THEN** the outcome SHALL be a stale fallback
- **AND** it SHALL instruct exact search and direct source reading
- **AND** it SHALL carry zero semantic hits

<!-- Scenario ID: skill-workflow.semantic-context-fallback-unavailable -->
#### Scenario: An unavailable service falls back

- **WHEN** injection is disabled, the code-search capability is absent, the
  transport cannot carry the query, or the service reports unavailable,
  not-configured, or overloaded
- **THEN** the outcome SHALL be an unavailable fallback with a distinct reason
  for each of those causes

<!-- Scenario ID: skill-workflow.semantic-context-fallback-mismatched -->
#### Scenario: A revision mismatch falls back

- **WHEN** the service reports that its index revision differs from the
  requested revision
- **THEN** the outcome SHALL be a mismatched fallback
- **AND** no result SHALL be presented as current

<!-- Scenario ID: skill-workflow.semantic-context-fallback-out-of-scope -->
#### Scenario: An out-of-scope outcome falls back

- **WHEN** the service rejects the requested scope, the package declares no
  usable read scope, or every returned hit fails the local scope re-check
- **THEN** the outcome SHALL be an out-of-scope fallback
- **AND** no hit outside the declared scope SHALL be rendered

<!-- Scenario ID: skill-workflow.semantic-context-fallback-nonblocking -->
#### Scenario: Fallback never blocks the coding job

- **WHEN** any fallback trigger fires
- **THEN** retrieval SHALL return a result rather than raise
- **AND** the coding job SHALL proceed
- **AND** an unrecognized service state SHALL map to an unavailable fallback
  rather than to injection

### Requirement: Opt-In Semantic Context Injection

Semantic context injection SHALL be disabled by default. With the feature
disabled, every coding job's assembled context SHALL be identical to its
behavior before this capability existed.

<!-- Scenario ID: skill-workflow.semantic-context-default-off -->
#### Scenario: Disabled injection changes nothing

- **WHEN** the semantic context injection switch is unset or set to any value
  outside the accepted truthy set
- **THEN** no semantic query SHALL be issued
- **AND** no `Semantic code context` section SHALL appear in the assembled
  context, not even a fallback notice

<!-- Scenario ID: skill-workflow.semantic-context-separate-switch -->
#### Scenario: Injection has its own switch

- **WHEN** the coordinator's code-search service is enabled
- **THEN** that alone SHALL NOT enable injection into coding jobs
- **AND** enabling injection SHALL require its own explicit switch
