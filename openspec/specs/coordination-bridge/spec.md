# coordination-bridge Specification

## Purpose

The `coordination-bridge` capability is the script-level HTTP fallback layer that lets non-MCP callers invoke coordinator operations (locks, work queue, handoffs, recall, archetype resolution) when the MCP transport is unavailable. It owns coordinator availability detection, transport selection, and the per-endpoint helper surface that orchestrator scripts, CI jobs, and skills depend on.

Specs that previously described the bridge as an implementation detail of `agent-coordinator` and `skill-consolidation` (see those specs for cross-capability touch points) MAY continue to reference it; this spec is the authoritative home for capability-level requirements.

## Requirements

### Requirement: Coordinator Availability Detection

`skills/coordination-bridge/scripts/check_coordinator.py` SHALL be the single canonical entry point that scripts and skills use to detect coordinator availability and produce capability flags.

- The script SHALL emit `COORDINATOR_AVAILABLE`, `COORDINATION_TRANSPORT` (`mcp|http|none`), and per-endpoint `CAN_*` flags in a stable, eval-friendly key=value format.
- Detection failures SHALL exit non-zero with diagnostic stderr output but MUST NOT print partial flags that callers could misinterpret as "available".
- The script SHALL be idempotent: repeated invocations within a session MUST produce the same flag values, modulo coordinator availability changes.

#### Scenario: MCP transport available
- **WHEN** the coordinator MCP server responds to a `discover_agents` ping
- **THEN** the script SHALL emit `COORDINATOR_AVAILABLE=true`, `COORDINATION_TRANSPORT=mcp`, and the discovered capability flags

#### Scenario: HTTP transport fallback
- **WHEN** the MCP transport is unavailable but the HTTP API at `COORDINATION_API_URL` responds to `/health`
- **THEN** the script SHALL emit `COORDINATOR_AVAILABLE=true`, `COORDINATION_TRANSPORT=http`, and the per-endpoint `CAN_*` flags

#### Scenario: No transport available
- **WHEN** neither transport responds
- **THEN** the script SHALL emit `COORDINATOR_AVAILABLE=false` and exit non-zero so callers can branch into standalone behavior

### Requirement: Uniform HTTP Helper Envelope

The bridge SHALL expose one helper function per coordinator HTTP endpoint with a uniform `{status, operation, response, ...}` return envelope so non-MCP callers can interpret success and failure without per-endpoint branching.

- Each helper SHALL never raise on transport errors; failures SHALL be reported via `status="failed"` and a diagnostic `error` field.
- Each helper SHALL log a structured warning (one line, JSON-friendly) on failure so multi-agent workflows can correlate bridge errors across runs.
- Helpers SHALL accept the same kwargs as the corresponding MCP tool where the API contract permits, so callers can swap transports without rewriting call sites.

#### Scenario: Successful HTTP operation
- **WHEN** a bridge helper (e.g., `try_lock`, `try_handoff_write`, `try_recall`, `try_remember`, `try_resolve_archetype_for_phase`) reaches the API and the response is 2xx with a parseable body
- **THEN** the helper SHALL return `{"status": "ok", "operation": "<name>", "response": <parsed-body>}`

#### Scenario: HTTP failure modes
- **WHEN** any of: connection error, timeout, non-2xx status, malformed JSON, or missing required fields occurs
- **THEN** the helper SHALL return `{"status": "failed", "operation": "<name>", "error": "<diagnostic>"}` and SHALL emit a structured warning to stderr
- **AND** the helper MUST NOT raise — non-MCP callers depend on the contract that bridge calls always return a dict

### Requirement: Capability Probe Bypass for Hot-Path Helpers

Hot-path helpers (those expected to run on every phase, e.g., `try_resolve_archetype_for_phase`) SHALL be permitted to bypass the generic capability-probe machinery so that every unrelated `try_*` call does not pay the probe cost on every invocation.

- A bypassing helper SHALL document the bypass in its docstring and tag the architectural decision in the introducing change's session log under `architectural: coordination-bridge`.
- The bypass SHALL only skip the capability probe; the helper MUST still respect the rest of the envelope contract (no raises, structured warnings on failure).

#### Scenario: Bypassing helper on coordinator without the endpoint
- **WHEN** a hot-path helper is called against a coordinator that lacks the underlying endpoint
- **THEN** the helper SHALL return `{"status": "failed", "operation": "<name>", "error": "<404-or-similar>"}` from the direct HTTP call and MUST NOT trigger a separate `CAN_*` probe round-trip
