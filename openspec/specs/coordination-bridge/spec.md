# coordination-bridge Specification

## Purpose

The `coordination-bridge` capability is the script-level HTTP fallback layer that lets non-MCP callers invoke coordinator operations (locks, work queue, handoffs, recall, archetype resolution) when the MCP transport is unavailable. It owns coordinator availability detection, transport selection, and the per-endpoint helper surface that orchestrator scripts, CI jobs, and skills depend on.

Specs that previously described the bridge as an implementation detail of `agent-coordinator` and `skill-consolidation` (see those specs for cross-capability touch points) MAY continue to reference it; this spec is the authoritative home for capability-level requirements.
## Requirements
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

### Requirement: Capability Probe Bypass for Hot-Path Helpers

Hot-path helpers (those expected to run on every phase, e.g., `try_resolve_archetype_for_phase`) SHALL be permitted to bypass the generic capability-probe machinery so that every unrelated `try_*` call does not pay the probe cost on every invocation.

- A bypassing helper SHALL document the bypass in its docstring and tag the architectural decision in the introducing change's session log under `architectural: coordination-bridge`.
- The bypass SHALL only skip the capability probe; the helper MUST still respect the rest of the envelope contract (no raises, structured warnings on failure).

#### Scenario: Bypassing helper on coordinator without the endpoint
- **WHEN** a hot-path helper is called against a coordinator that lacks the underlying endpoint
- **THEN** the helper SHALL return `{"status": "failed", "operation": "<name>", "error": "<404-or-similar>"}` from the direct HTTP call and MUST NOT trigger a separate `CAN_*` probe round-trip

