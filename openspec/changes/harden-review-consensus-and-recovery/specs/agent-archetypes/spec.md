## ADDED Requirements

### Requirement: Review Dispatch Applies Resolved Reviewer Routing

Every multi-vendor review request SHALL resolve the `reviewer` archetype through the coordinator-owned phase/model mapping and SHALL pass the provider-specific model plus thinking setting to each supported adapter.

Routing precedence SHALL be: explicit resolved routing context; autopilot review-phase mapping; default `reviewer` archetype for review-mode calls without a phase (including direct CLI and pull-request review); then static vendor configuration only when coordinator and local archetype resolution both fail. Quick-mode dispatch SHALL retain static routing unless its caller explicitly supplies routing context.

#### Scenario: Pi review uses premium mapping
- **WHEN** a plan or implementation review is dispatched to Pi with the default `reviewer` archetype
- **THEN** routing SHALL resolve the configured reviewer/premium Pi model rather than the static Pi standard default
- **AND** the manifest SHALL record the requested reviewer tier and resolved provider model

#### Scenario: Provider model differs from static default
- **WHEN** reviewer resolution returns a provider model or thinking value different from the agent's static CLI default
- **THEN** CLI, SDK, and async dispatch paths SHALL apply the resolved values using provider configuration
- **AND** no dispatcher branch SHALL hard-code a provider model identifier

#### Scenario: Reviewer resolution is unavailable
- **WHEN** coordinator and local archetype resolution both fail
- **THEN** dispatch MAY use the static configured vendor default
- **AND** the manifest SHALL record a null/unresolved archetype plus the fallback reason

#### Scenario: Pull-request review without autopilot phase
- **WHEN** merge-pull-requests invokes review-mode dispatch without an autopilot phase
- **THEN** the orchestrator SHALL resolve the default `reviewer` archetype for each provider
- **AND** explicit caller routing, when present, SHALL take precedence

#### Scenario: Quick task preserves non-review routing
- **WHEN** quick-task invokes quick-mode dispatch without explicit routing context
- **THEN** the orchestrator SHALL use the existing static quick-task model configuration
- **AND** it SHALL NOT infer the `reviewer` archetype solely from the shared dispatcher API

### Requirement: Review Routing Provenance

Review results SHALL distinguish requested logical routing from the concrete provider execution selected for each attempt.

Provider dispatch configuration SHALL define any supported thinking flag plus an optional allowed-value translation map. Same-provider fallback entries SHALL either declare model-plus-thinking together or explicitly inherit the logical request's thinking setting. A non-null thinking setting without a supported translation SHALL fail the attempt with a configuration error and SHALL remain quorum-ineligible; it SHALL NOT be silently omitted.

#### Scenario: Fallback model is used
- **WHEN** a review starts with a resolved premium model and later succeeds on a configured fallback model
- **THEN** provenance SHALL retain the requested archetype/tier and every attempted provider model
- **AND** the terminal result SHALL identify the actual successful model, thinking setting, and fallback reason

#### Scenario: Unsupported thinking flag
- **WHEN** a resolved thinking setting cannot be represented by a provider adapter
- **THEN** the adapter SHALL record requested thinking, null applied thinking, translation status `unsupported`, and a configuration failure
- **AND** it SHALL not silently claim that the requested thinking setting was applied
- **AND** replacement/quorum policy MAY recover through another eligible vendor, but the failed attempt SHALL not count

#### Scenario: Same-provider fallback declares thinking behavior
- **WHEN** a fallback model is attempted after reviewer routing resolved a non-null thinking setting
- **THEN** provider configuration SHALL either supply the fallback's explicit thinking value or declare inheritance of the requested value
- **AND** the manifest SHALL record the actual applied value and translation status
