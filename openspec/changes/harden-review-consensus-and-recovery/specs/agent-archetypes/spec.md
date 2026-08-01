## ADDED Requirements

### Requirement: Review Dispatch Applies Resolved Reviewer Routing

Every multi-vendor review request SHALL resolve the `reviewer` archetype through the coordinator-owned phase/model mapping and SHALL pass the provider-specific model plus thinking setting to each supported adapter.

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

### Requirement: Review Routing Provenance

Review results SHALL distinguish requested logical routing from the concrete provider execution selected for each attempt.

#### Scenario: Fallback model is used
- **WHEN** a review starts with a resolved premium model and later succeeds on a configured fallback model
- **THEN** provenance SHALL retain the requested archetype/tier and every attempted provider model
- **AND** the terminal result SHALL identify the actual successful model, thinking setting, and fallback reason

#### Scenario: Unsupported thinking flag
- **WHEN** a resolved thinking setting cannot be represented by a provider adapter
- **THEN** the adapter SHALL record the unsupported translation and follow configured fallback policy
- **AND** it SHALL not silently claim that the requested thinking setting was applied
