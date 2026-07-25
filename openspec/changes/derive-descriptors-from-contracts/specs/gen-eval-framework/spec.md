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

The guard SHALL fail when the generated artifact declares zero operations.

The guard SHALL fail when the generated artifact's operation count differs
from the contract's operation count.

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

The report SHALL continue to emit the flat interface list for backward
compatibility during the deprecation window, computed from the operation model.

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
declared surface across its HTTP, MCP, and CLI bindings, with per-surface
counts matching the descriptor rather than a figure duplicated into this spec.

Template scenarios MUST include both success and failure paths for at minimum:
lock lifecycle, work queue operations, auth boundaries, cross-interface
consistency, and multi-agent contention.

A dogfood descriptor whose declared surface is non-empty MUST achieve 80%+
interface coverage (unique interfaces exercised by at least one template
scenario / total declared interfaces × 100) with template scenarios alone. A
descriptor whose declared surface is empty MUST fail rather than report
coverage, since a vacuous coverage figure is indistinguishable from full
coverage.

gen-eval MUST maintain a tool descriptor for its own CLI surface, derived from
a CLI contract, and MUST evaluate it as a blocking gate.

#### Scenario: Dogfood descriptor covers the full agent-coordinator surface

- **WHEN** the framework loads the agent-coordinator dogfood descriptor
- **THEN** it SHALL register every HTTP endpoint, MCP tool, and CLI command the
  descriptor declares
- **AND** the registered counts SHALL match the descriptor's declared counts

#### Scenario: Template scenarios include failure paths for core operations

- **WHEN** the dogfood template scenario set is inspected for coverage
- **THEN** lock lifecycle, work queue, auth boundaries, cross-interface
  consistency, and multi-agent contention SHALL each have at least one
  failure-path scenario

#### Scenario: Template-only run achieves 80% interface coverage

- **WHEN** a `template-only` run completes against a dogfood descriptor with a
  non-empty declared surface
- **THEN** the interface coverage percentage SHALL be at least 80%

#### Scenario: An empty declared surface fails rather than reporting coverage

- **WHEN** a dogfood run completes against a descriptor declaring zero
  interfaces
- **THEN** the run SHALL fail
- **AND** it SHALL NOT report a coverage percentage implying full coverage

#### Scenario: gen-eval evaluates its own CLI surface

- **WHEN** gen-eval's own tool descriptor is evaluated
- **THEN** its declared surface SHALL be non-empty
- **AND** the evaluation SHALL gate CI
