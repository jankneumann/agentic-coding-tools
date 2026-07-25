## ADDED Requirements

### Requirement: Independently runnable deterministic context producers

The system SHALL register deterministic context producers for documentation
inventories, API contracts and generated bindings, decision timelines, and
OpenSpec projections. Each producer SHALL expose a stable producer ID, canonical
owner, producer version, declared inputs, and declared managed outputs.

<!-- Scenario ID: project-context-refresh.producer-discovery -->
#### Scenario: Producer discovery

- **WHEN** a caller lists configured deterministic context producers
- **THEN** the registry SHALL return `documentation.inventory`,
  `api.contracts`, `decisions.timeline`, and `openspec.projection`
- **AND** each entry SHALL identify the existing skill, command, or module that
  canonically owns its domain
- **AND** entries SHALL be ordered by stable producer ID

### Requirement: Side-effect-free deterministic check mode

Each deterministic producer SHALL support `generate` and `check` modes for an
explicit repository and full source Git revision. Check mode SHALL render
expected output without changing the checkout and SHALL report every repository
artifact whose bytes differ through the canonical ri-06 `ProducerResult`.

<!-- Scenario ID: project-context-refresh.precise-drift -->
#### Scenario: Drift is reported precisely

- **WHEN** one managed output differs from output rendered for the requested
  revision
- **THEN** check mode SHALL return that path as a canonical repository-artifact
  record with its expected change kind and digest
- **AND** SHALL include a failed validation plus actionable remediation
- **AND** SHALL use `degraded` with an explicit check-mode fallback rather than
  claim the result is fresh
- **AND** SHALL leave tracked and untracked checkout state unchanged

<!-- Scenario ID: project-context-refresh.repeat-generation -->
#### Scenario: Repeat generation is byte-identical

- **WHEN** a producer generates output twice for the same revision, inputs, and
  producer version
- **THEN** the second run SHALL produce byte-identical managed artifacts
- **AND** a subsequent check SHALL return `fresh` with no artifact changes

### Requirement: Stable producer provenance

Generated context artifacts SHALL carry the source Git revision, stable producer
ID, and producer version without embedding wall-clock-derived repository
content. For mixed-ownership Markdown files, metadata and generated content SHALL
remain inside declared marker regions.

<!-- Scenario ID: project-context-refresh.preserve-prose -->
#### Scenario: Hand-authored documentation is preserved

- **WHEN** the documentation producer updates a generated inventory block
- **THEN** every byte outside the matching generated marker pair SHALL remain
  unchanged
- **AND** malformed or unbalanced marker pairs SHALL fail without writing

### Requirement: Canonical producer results

Each producer invocation SHALL return the strict ri-06
`project-context-runtime` `ProducerResult` model and SHALL validate against
`context-refresh-types.schema.json#/$defs/ProducerResult`. ri-05 MUST NOT define
an incompatible producer-result object.

Repository artifacts, validations, remediation, fallbacks, and safe errors SHALL
follow the canonical schema's conditional rules and deterministic ordering.

<!-- Scenario ID: project-context-refresh.canonical-result -->
#### Scenario: Result validates without translation

- **WHEN** any registered adapter completes generation or checking
- **THEN** its returned object SHALL validate directly as an ri-06
  `ProducerResult`
- **AND** ri-07 SHALL NOT require a field-name or status translation layer before
  recording it

<!-- Scenario ID: project-context-refresh.actionable-failure -->
#### Scenario: Producer failure remains actionable

- **WHEN** a producer cannot render or compare its managed output
- **THEN** its status SHALL be `failed`
- **AND** it SHALL include a failed validation, bounded safe error, and at least
  one remediation entry
- **AND** the result SHALL not claim any mismatched artifact is fresh

<!-- Scenario ID: project-context-refresh.optional-unavailable -->
#### Scenario: Optional unavailable producer declares fallback

- **WHEN** a registry entry marks a producer optional and its owner is not
  configured
- **THEN** its status SHALL be `not-configured`
- **AND** it SHALL include a skipped validation, remediation, and explicit
  fallback conforming to the canonical contract

### Requirement: Documentation sync lifecycle is superseded

The `add-update-documentation-skill` change SHALL be marked superseded by this
change across its proposal, design, task plan, work packages, and spec delta.
Its marker-preserving documentation producer behavior SHALL be retained here,
while its standalone hook, cleanup, post-merge, validate-feature, and auto-commit
lifecycle SHALL NOT remain executable.

<!-- Scenario ID: project-context-refresh.documentation-superseded -->
#### Scenario: Superseded change cannot dispatch

- **WHEN** a workflow inspects `add-update-documentation-skill`
- **THEN** it SHALL find no executable task or work package
- **AND** it SHALL find no normative delta directing hook, cleanup, post-merge,
  validate-feature, or auto-commit integration
- **AND** it SHALL identify this change as the replacement

<!-- Scenario ID: project-context-refresh.shared-convergence-owner -->
#### Scenario: Only the shared lifecycle owns later convergence

- **WHEN** project-context refresh integration is planned or implemented
- **THEN** callers SHALL use the registered documentation producer
- **AND** SHALL not invoke a competing post-merge documentation auto-commit path

### Requirement: OpenSpec checks do not mutate canonical specs

The OpenSpec projection producer SHALL reuse canonical delta parsing and merge
semantics to compute expected capability changes outside the live
`openspec/specs/` tree.

<!-- Scenario ID: project-context-refresh.openspec-projection -->
#### Scenario: Active deltas are projected

- **WHEN** active delta specs would change one or more canonical capability specs
- **THEN** check mode SHALL report the expected repository-artifact changes plus
  a failed validation
- **AND** SHALL leave canonical specs, active changes, and archives unchanged
- **AND** SHALL not bypass the active-agent guard or cleanup-feature ownership
