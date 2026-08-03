# gen-eval-framework — contract-derived descriptors

## ADDED Requirements

### Requirement: Contract As Descriptor Source Of Truth

Descriptors SHALL be derived from a machine-readable contract, and runtime
introspection of a running implementation SHALL NOT be used to populate a
descriptor's declared surface.

The contract SHALL live under `openspec/contracts/<capability>/` — `openapi/`
for service contracts, `cli/` for tool contracts — which is the canonical
location that survives change archival.

Runtime introspection SHALL be used only to verify that an implemented surface
is a subset of its contract, per the Implemented Surface Subset Verification
requirement.

#### Scenario: Descriptor derives from a contract

- **WHEN** a descriptor declares a contract reference
- **THEN** the framework SHALL populate the declared surface from that contract
- **AND** it SHALL NOT invoke the implementation to enumerate that surface

#### Scenario: Unreachable implementation does not shrink the declared surface

- **WHEN** a descriptor is loaded and the implementation it describes is broken,
  absent, or unreachable
- **THEN** the declared surface SHALL be unchanged from the contract
- **AND** coverage SHALL be computed against that unchanged declared surface

### Requirement: Service And Tool Descriptor Archetypes

The framework SHALL distinguish a service descriptor from a tool descriptor,
and SHALL apply the coverage and lifecycle semantics appropriate to each.

A service descriptor describes a system whose surface is projected across HTTP
and MCP bindings from one operation set; its contract is OpenAPI and its
coverage unit is the operation.

A tool descriptor describes a program's own invocation surface; its contract is
a CLI contract and its coverage unit is the command or flag. A tool descriptor
SHALL NOT require service lifecycle configuration.

Both archetypes SHALL be loadable alongside the existing hand-authored
descriptor format, which remains supported and is deprecated.

#### Scenario: Tool descriptor requires no lifecycle configuration

- **WHEN** a tool descriptor is loaded
- **THEN** the framework SHALL NOT require startup, health-check, or teardown
  configuration
- **AND** the orchestrator SHALL skip startup, health check, seeding, and
  teardown

#### Scenario: Hand-authored descriptor still loads

- **WHEN** a descriptor declares no contract reference
- **THEN** the framework SHALL load it using the existing hand-authored format
- **AND** it SHALL emit a deprecation warning naming the contract-derived
  replacement

### Requirement: Descriptor Derivation Drift Guard

Derived descriptors SHALL be generated as checked-in artifacts, and a
`--check` mode SHALL exit non-zero when a checked-in artifact differs from
what the generator produces from the current contract.

The guard SHALL fail when the generated artifact declares zero coverage units.

The guard SHALL fail when the generated artifact's coverage-unit count differs
from the contract's coverage-unit count.

The coverage unit SHALL be the operation for a service descriptor, and the flag,
positional argument, or named subcommand for a tool descriptor. The guard SHALL
NOT count commands as coverage units for a tool descriptor.

#### Scenario: Drift between contract and checked-in descriptor fails

- **WHEN** a contract is changed and the derived descriptor is not regenerated
- **THEN** `--check` SHALL exit non-zero
- **AND** it SHALL report which artifact drifted

#### Scenario: An empty derived descriptor fails rather than passing trivially

- **WHEN** derivation produces a descriptor declaring zero operations
- **THEN** the guard SHALL fail on the non-emptiness assertion
- **AND** it SHALL NOT report success on the grounds that the checked-in copy
  is also empty

#### Scenario: Operation count mismatch fails

- **WHEN** a derived descriptor declares a different number of operations than
  its contract
- **THEN** the guard SHALL fail
- **AND** it SHALL report both counts

#### Scenario: A tool contract declaring commands but no coverage units fails

- **WHEN** a tool contract declares one or more commands and zero flags,
  positionals, and named subcommands
- **THEN** the guard SHALL fail on the non-emptiness assertion
- **AND** it SHALL NOT report success on the grounds that the command count is
  non-zero and matches

### Requirement: Implemented Surface Subset Verification

The framework SHALL verify that an implementation exposes no surface absent
from its contract, for HTTP, MCP, and CLI surfaces.

HTTP surfaces SHALL be introspected from the application's generated OpenAPI
document, MCP surfaces from the server's tool listing, and CLI surfaces from
the argument parser's declared actions.

A surface element present in the implementation but absent from the contract
SHALL be reported as a contract violation.

#### Scenario: Undocumented endpoint is reported

- **WHEN** an implementation exposes an HTTP route absent from its contract
- **THEN** verification SHALL report a contract violation naming that route

#### Scenario: Undocumented CLI flag is reported

- **WHEN** an argument parser declares a flag absent from the tool contract
- **THEN** verification SHALL report a contract violation naming that flag

#### Scenario: Verification distinguishes excess from omission

- **WHEN** verification runs against a conformant implementation
- **THEN** it SHALL report no violation
- **AND** an implementation missing a contracted element SHALL be reported by
  coverage rather than by subset verification

### Requirement: Operation And Surface Coverage Model

Coverage SHALL be keyed on the operation, with per-surface exposure and
per-surface coverage recorded separately.

A surface that does not expose a given operation SHALL be recorded as not
exposed, and SHALL NOT count as an uncovered surface for that operation.

An operation SHALL be reported as unevaluated when no surface that exposes it
was exercised by any scenario.

Each exposed surface entry SHALL name the surface-local element that serves the
operation, and one element MAY serve more than one operation. Exercising a bound
element SHALL count as coverage of every operation bound to it.

The binding SHALL be expressible in the contract itself: a service contract
SHALL declare it on the operation, and a tool contract SHALL declare it on the
command. A binding that exists only in derived output and cannot be authored in
a contract SHALL NOT satisfy this requirement.

The identifiers recorded as tested SHALL be drawn from the same vocabulary as
the declared surface, so that a tested element matches its declared counterpart.

The framework SHALL provide a coverage threshold that fails a run when interface
coverage falls below it, separately from the pass-rate threshold.

The report SHALL continue to emit the flat interface list and the per-interface
coverage map for backward compatibility during the deprecation window, both
computed from the operation model.

#### Scenario: One operation tested via one surface is not three gaps

- **WHEN** an operation exposed on HTTP, MCP, and CLI is exercised via HTTP only
- **THEN** the operation SHALL be reported as covered
- **AND** the report SHALL record MCP and CLI as exposed but not covered

#### Scenario: A surface that does not expose an operation is not a gap

- **WHEN** an operation is exposed on HTTP but not on CLI
- **THEN** the CLI surface SHALL be recorded as not exposed for that operation
- **AND** it SHALL NOT contribute to the unevaluated set

#### Scenario: Flag-only tool surfaces are nameable

- **WHEN** a tool descriptor is derived from a CLI contract for a program with
  no subcommands
- **THEN** each contracted flag SHALL be a nameable coverage unit
- **AND** the declared surface SHALL be non-empty

#### Scenario: The many-to-one binding is authorable in a contract

- **WHEN** two operations in a service contract declare the same surface element
- **THEN** the contract SHALL validate
- **AND** derivation SHALL emit that element once rather than one element per
  operation

#### Scenario: One surface element serving two operations is covered once

- **WHEN** two operations bind to the same MCP tool and a scenario exercises
  that tool
- **THEN** both operations SHALL be reported as covered on the MCP surface
- **AND** subset verification SHALL NOT report that tool as undocumented
- **AND** it SHALL NOT report the two operations as omitted tools

#### Scenario: A flag exercised by a scenario is recorded as covered

- **WHEN** a scenario step invokes a tool with a contracted flag among its
  arguments
- **THEN** that flag SHALL appear in the tested identifier set
- **AND** it SHALL match the declared coverage unit of the same name

#### Scenario: Coverage below the threshold fails the run

- **WHEN** a run completes with interface coverage below the configured
  coverage threshold
- **THEN** the framework SHALL exit non-zero
- **AND** it SHALL do so independently of whether the pass-rate threshold was met

### Requirement: Descriptor Reclamation Is Announced

A previously-aliased type name assigned to a different type SHALL resolve, at
package level, to the new type, and SHALL be recorded in a downstream notice
naming both the previous and the new meaning.

Reclaiming a Python export name SHALL NOT, on that account alone, increment the
descriptor contract version. The published JSON Schema contract is unchanged by
which Python object a name binds to — the version tracks the schema, not the
package's export table. Incrementing it for a reclamation would signal a schema
change to every downstream consumer that validates against it, with nothing for
them to react to; the downstream notice is what carries a rename that only
affects importers.

A reclaimed name SHALL NOT be left resolving to the superseded type at package
level while resolving to the new type within its defining module.

#### Scenario: A reclaimed name is announced rather than silently rebound

- **WHEN** a descriptor archetype takes a name that previously denoted an
  element or container type
- **THEN** a downstream notice SHALL name both the previous and the new meaning
- **AND** the descriptor contract version SHALL NOT be incremented on that
  account alone

#### Scenario: Package-level export resolves to the reclaimed type

- **WHEN** a caller imports a reclaimed name from the package root
- **THEN** it SHALL receive the new archetype
- **AND** it SHALL NOT receive the superseded element or container type

## MODIFIED Requirements

### Requirement: Interface Descriptor

The framework MUST accept an interface descriptor (YAML) that declaratively
describes a project's testable surface including HTTP endpoints, MCP tools, CLI
commands, and state verifiers.

Service lifecycle configuration (startup command, health check, teardown
command, health check timeout, retry count) MUST be optional. A descriptor for
a project with nothing to start MUST be loadable without it, and the
orchestrator MUST skip startup, health check, seeding, and teardown when it is
absent.

The framework MUST derive a descriptor's declared surface from a contract —
an OpenAPI document for service descriptors, a CLI contract for tool
descriptors. The framework MUST NOT populate a declared surface by
introspecting a running implementation; implementation introspection is
reserved for subset verification.

The descriptor format MUST be project-agnostic — no hardcoded references to
agent-coordinator internals.

#### Scenario: Descriptor validates project surface

- **WHEN** the framework loads a YAML interface descriptor for a project
- **THEN** it SHALL correctly identify HTTP endpoints, MCP tools, CLI commands,
  and state verifiers

#### Scenario: Descriptor supports optional service lifecycle config

- **WHEN** a descriptor declares startup command, health check, and teardown
- **THEN** the orchestrator SHALL use those settings including retry count and
  timeout

#### Scenario: Descriptor without lifecycle config loads and runs

- **WHEN** a descriptor omits service lifecycle configuration
- **THEN** the framework SHALL load it without error
- **AND** the orchestrator SHALL skip startup, health check, seeding, and
  teardown

#### Scenario: Declared surface comes from the contract

- **WHEN** a descriptor references an OpenAPI or CLI contract
- **THEN** the declared surface SHALL be derived from that contract
- **AND** a running implementation SHALL NOT be consulted to enumerate it

### Requirement: Dogfood

The agent-coordinator dogfood descriptor MUST cover the coordinator's full
declared surface across its HTTP, MCP, and CLI bindings: at minimum 38 HTTP
endpoints, 39 MCP tools, and 37 CLI commands.

Template scenarios MUST include both success and failure paths for at minimum:
lock lifecycle, work queue operations, auth boundaries, cross-interface
consistency, and multi-agent contention.

A **service** dogfood descriptor whose declared surface is non-empty MUST
achieve 80%+ interface coverage (unique interfaces exercised by at least one
template scenario / total declared interfaces × 100) with template scenarios
alone.

A **tool** dogfood descriptor MUST instead satisfy a completeness rule: every
contracted coverage unit MUST be either exercised by at least one scenario or
declared as an explicit exclusion carrying a stated reason. A coverage unit that
is neither exercised nor excluded MUST fail the gate.

A descriptor whose declared surface is empty MUST fail rather than report
coverage, since a vacuous coverage figure is indistinguishable from full
coverage.

gen-eval MUST maintain a tool descriptor for its own CLI surface, derived from
a CLI contract, and MUST evaluate it as a blocking gate.

#### Scenario: Dogfood descriptor covers the full agent-coordinator surface

- **WHEN** the framework loads the agent-coordinator dogfood descriptor
- **THEN** it SHALL register every HTTP endpoint, MCP tool, and CLI command the
  descriptor declares
- **AND** the registered counts SHALL be at least 38 HTTP endpoints, 39 MCP
  tools, and 37 CLI commands

#### Scenario: Template scenarios include failure paths for core operations

- **WHEN** the dogfood template scenario set is inspected for coverage
- **THEN** lock lifecycle, work queue, auth boundaries, cross-interface
  consistency, and multi-agent contention SHALL each have at least one
  failure-path scenario

#### Scenario: Template-only run achieves 80% interface coverage

- **WHEN** a `template-only` run completes against a **service** dogfood
  descriptor with a non-empty declared surface
- **THEN** the interface coverage percentage SHALL be at least 80%

#### Scenario: An unexercised, unexcluded tool coverage unit fails the gate

- **WHEN** a tool dogfood descriptor declares a coverage unit that no scenario
  exercises and that carries no exclusion entry
- **THEN** the gate SHALL fail naming that unit
- **AND** a percentage above any threshold SHALL NOT satisfy the gate in its place

#### Scenario: An excluded coverage unit states why

- **WHEN** a contracted coverage unit is declared as an exclusion
- **THEN** the exclusion SHALL carry a stated reason
- **AND** an exclusion without a reason SHALL fail the gate

#### Scenario: An empty declared surface fails rather than reporting coverage

- **WHEN** a dogfood run completes against a descriptor declaring zero
  interfaces
- **THEN** the run SHALL fail
- **AND** it SHALL NOT report a coverage percentage implying full coverage

#### Scenario: gen-eval evaluates its own CLI surface

- **WHEN** gen-eval's own tool descriptor is evaluated
- **THEN** its declared surface SHALL be non-empty
- **AND** the evaluation SHALL gate CI
