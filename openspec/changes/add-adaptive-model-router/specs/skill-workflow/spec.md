# skill-workflow Specification (delta)

## MODIFIED Requirements

### Requirement: CLI Configuration Schema

Each agent entry in `agents.yaml` SHALL support an optional `cli` section containing harness
mechanics: `command`, `dispatch_modes`, `model_flag`, prompt-delivery configuration, polling
configuration, and any required credential environment variable. The section SHALL NOT accept
`model` or `model_fallbacks`; the dispatcher SHALL receive the concrete ordered model chain from
task/archetype resolution in `archetypes.yaml`.

#### Scenario: Agent with no CLI section

- **GIVEN** an agent entry in `agents.yaml` without a `cli` section
- **WHEN** the ReviewOrchestrator loads agent config
- **THEN** no CLI adapter SHALL be created for that agent

#### Scenario: Model flag remains harness mechanics

- **GIVEN** a CLI entry declares `model_flag: --model` without a model value
- **WHEN** a resolved archetype route selects a concrete model
- **THEN** the adapter SHALL append `--model <resolved-model>` using those two separate sources

#### Scenario: Concrete CLI model in registry is rejected

- **GIVEN** a CLI entry declares `model` or `model_fallbacks`
- **WHEN** agent configuration is validated
- **THEN** validation SHALL fail before dispatch

### Requirement: Model Fallback on Capacity Errors

When a vendor returns a capacity error, the adapter SHALL retry with the remaining models from the
ordered chain resolved from `archetypes.yaml` for the selected agent, dispatch kind, and
task/archetype tier. The adapter SHALL NOT read model fallbacks from `agents.yaml`.

#### Scenario: Primary model exhausted and fallback succeeds

- **GIVEN** a resolved route contains a primary model followed by a fallback
- **WHEN** the primary returns a capacity error
- **THEN** the adapter SHALL retry the fallback using the harness's configured `model_flag`
- **AND** successful output SHALL be used normally

#### Scenario: All resolved models exhausted

- **GIVEN** every model in the resolved chain returns a capacity error
- **WHEN** the chain is exhausted
- **THEN** the vendor SHALL be marked failed with every attempted model reported

#### Scenario: Sync async and SDK dispatch use the same chain

- **GIVEN** the same agent/task route is exercised through synchronous CLI, asynchronous CLI, and SDK
- **WHEN** each path encounters a capacity error
- **THEN** each path SHALL try the same resolved models in the same order

### Requirement: Configurable Model Fallback Chains

Static model fallback chains SHALL be configured only in `archetypes.yaml`, keyed by exact agent
harness, dispatch kind, and logical tier. Each entry SHALL be a non-empty ordered `ModelSpec`
chain whose items contain a concrete model and optional thinking level. The adapter SHALL NOT
hardcode model names or use ambient harness defaults.

#### Scenario: Dispatcher reads the resolved archetype chain

- **GIVEN** `archetypes.yaml` declares an ordered model chain for `grok-local`, CLI, premium
- **WHEN** a reviewer task resolves to that route
- **THEN** the adapter SHALL use that chain in order

### Requirement: SDK Configuration in agents.yaml

Each agent entry in `agents.yaml` SHALL support an optional `sdk` section containing SDK
mechanics only: `package`, `method`, `api_key_env`, and `max_tokens`. It SHALL NOT accept
`model` or `model_fallbacks`. SDK dispatch SHALL receive its concrete ordered model chain from
`archetypes.yaml`, and `get_dispatch_configs()` SHALL expose no concrete model policy from
`agents.yaml`.

#### Scenario: Agent with SDK mechanics and resolved model route

- **GIVEN** an agent declares SDK package and method metadata in `agents.yaml`
- **AND** `archetypes.yaml` declares its SDK model chain for the task-selected tier
- **WHEN** SDK dispatch is initialized
- **THEN** the SDK adapter SHALL combine the mechanics with that resolved chain

#### Scenario: Agent without SDK configuration

- **GIVEN** an agent has no `sdk` section
- **WHEN** dispatch configurations are loaded
- **THEN** that agent SHALL be excluded from SDK dispatch


### Requirement: Resolved Route Projection

Resolved dispatch configuration SHALL project the task-selected route only after combining
`agents.yaml` harness mechanics with the `archetypes.yaml` model chain. Local discovery, HTTP,
MCP, and the coordination bridge SHALL expose the same `agent_id`, `dispatch_kind`, selected
`ModelSpec`, and ordered `capacity_fallbacks`; none may re-project legacy registry model fields.

#### Scenario: Local, HTTP, MCP, and bridge projections agree

- **GIVEN** an agent, dispatch kind, archetype, and tier resolve a valid static route
- **WHEN** the route is requested through local discovery, HTTP, MCP, and the coordination bridge
- **THEN** every transport SHALL return the same selected model, thinking level, and fallback order
- **AND** every response SHALL identify the same `agent_id` and `dispatch_kind`
- **AND** the projection SHALL NOT source concrete models from `agents.yaml`

#### Scenario: Health reporting does not invent an ambient model

- **GIVEN** vendor health runs without a resolved task route
- **WHEN** it reports harness availability
- **THEN** it SHALL report mechanics and availability without inventing a model identifier
- **AND** when a route is supplied, any reported model SHALL come from that resolved chain
