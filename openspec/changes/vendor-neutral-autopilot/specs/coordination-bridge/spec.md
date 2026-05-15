## MODIFIED Requirements

### Requirement: Coordinator Availability Detection

`skills/coordination-bridge/scripts/check_coordinator.py` SHALL be the single canonical entry point that scripts and skills use to detect coordinator availability and produce capability flags.

The script SHALL detect coordinator availability without requiring Claude Code to be installed. Detection order SHALL be:

1. HTTP coordinator health and route probes using `COORDINATION_API_URL` or the configured default URL.
2. Provider-neutral explicit coordinator configuration from environment.
3. Provider-native MCP configuration when available, including Claude MCP configuration.
4. Unavailable result with `COORDINATION_TRANSPORT=none`.

The script SHALL emit `COORDINATOR_AVAILABLE`, `COORDINATION_TRANSPORT` (`mcp|http|none`), and per-endpoint `CAN_*` flags in JSON mode and in the stable text mode expected by existing callers.

#### Scenario: HTTP transport available without Claude CLI

- **GIVEN** the `claude` command is not installed
- **AND** the HTTP coordinator at `COORDINATION_API_URL` responds to `/health`
- **WHEN** `check_coordinator.py --json` runs
- **THEN** it SHALL emit `COORDINATOR_AVAILABLE=true`
- **AND** it SHALL emit `COORDINATION_TRANSPORT=http`
- **AND** it SHALL NOT attempt `claude mcp get coordination`

#### Scenario: No provider-native MCP config exists

- **GIVEN** no provider-native MCP configuration is present
- **AND** HTTP coordinator detection fails
- **WHEN** `check_coordinator.py --json` runs
- **THEN** it SHALL emit `COORDINATOR_AVAILABLE=false`
- **AND** it SHALL emit `COORDINATION_TRANSPORT=none`
- **AND** the diagnostic SHALL not name Claude as the only supported MCP path

### Requirement: Uniform HTTP Helper Envelope

The bridge SHALL expose helper functions for coordinator HTTP endpoints with a uniform failure contract so non-MCP callers can interpret success and failure without provider-specific branching.

Helpers SHALL never raise on transport errors; failures SHALL be reported through a structured failure result or `None` only where legacy helper signatures already require `None`.

#### Scenario: Archetype helper includes provider context in warnings

- **WHEN** `try_resolve_archetype_for_phase` fails while resolving for provider `codex`
- **THEN** the structured warning SHALL include the phase and provider
- **AND** it SHALL mention provider model mapping as a mitigation path
