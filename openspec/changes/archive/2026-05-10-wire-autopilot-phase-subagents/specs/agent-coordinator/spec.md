# Agent Coordinator — Spec Delta: AgentInfo Phase Archetype + Status Reporter Wiring

## MODIFIED Requirements

### Requirement: Status Report Payload Phase Archetype Field

The `POST /status/report` endpoint SHALL accept and persist a `phase_archetype` field in the request body, alongside the existing `phase` field. The autopilot status reporter (`agent-coordinator/scripts/report_status.py`) SHALL read `phase_archetype` from `loop-state.json` and include it in every status report POST.

The field:
- SHALL be optional (omitting it SHALL not cause `400` errors — older clients remain compatible).
- SHALL be persisted in the agent-status table or equivalent so observability dashboards can query "which archetype was active in phase X for change Y".
- SHALL be exposed in `GET /status/agents` (or the corresponding listing endpoint) as part of each agent's current-phase summary.
- SHALL be exposed in `GET /discovery/agents` as part of each `AgentInfo` record.

The status reporter SHALL:
- Read `phase_archetype` from `loop-state.json` at every Stop-hook invocation.
- Include it in the POST body when non-null.
- Omit it (or send `null`) when no archetype was resolved for the current phase.

#### Scenario: Status report with phase_archetype is persisted

- **WHEN** an autopilot client sends `POST /status/report` with `{"agent_id": "...", "change_id": "...", "phase": "PLAN", "phase_archetype": "architect"}`
- **THEN** the response status SHALL be `200`
- **AND** subsequent calls to `GET /status/agents` SHALL return `phase_archetype: "architect"` for that agent
- **AND** subsequent calls to `GET /discovery/agents` SHALL return `phase_archetype: "architect"` for that agent

#### Scenario: Status report without phase_archetype is accepted

- **WHEN** an older autopilot client sends `POST /status/report` without `phase_archetype`
- **THEN** the response status SHALL be `200`
- **AND** the persisted record SHALL have `phase_archetype = NULL`

#### Scenario: report_status.py reads phase_archetype from loop-state.json

- **GIVEN** `loop-state.json` contains `{"current_phase": "PLAN", "phase_archetype": "architect", ...}`
- **WHEN** `report_status.py` is invoked by the Stop hook
- **THEN** the POST body SHALL include `"phase_archetype": "architect"`
- **AND** the coordinator SHALL persist the value on the agent's session row

#### Scenario: report_status.py handles missing phase_archetype gracefully

- **GIVEN** `loop-state.json` lacks the `phase_archetype` key (older state file)
- **WHEN** `report_status.py` reads the file
- **THEN** the POST body SHALL omit `phase_archetype` (or send `null`)
- **AND** the call SHALL succeed without error

#### Scenario: report_status.py drops invalid phase_archetype values from POST

- **GIVEN** `loop-state.json` contains a `phase_archetype` value not in the enum (e.g., `"malicious_value"` introduced by local file tampering)
- **WHEN** `report_status.py` reads the file
- **THEN** `report_status.py` SHALL validate the value against the allowed enum (`architect`, `reviewer`, `implementer`, `analyst`, `runner`, `null`)
- **AND** if invalid, SHALL send `null` in the POST body instead of forwarding the invalid value
- **AND** SHALL log a structured warning identifying the invalid value

#### Scenario: POST /status/report rejects out-of-enum phase_archetype values

- **WHEN** a client sends `POST /status/report` with `phase_archetype: "not_an_archetype"`
- **THEN** the response status SHALL be `422` (validation error)
- **AND** the persisted database row SHALL be unchanged
- **AND** the rejection SHALL come from the API layer (Pydantic enum validation), independently of any database constraint

## ADDED Requirements

### Requirement: AgentInfo Phase Archetype Persistence

The `AgentInfo` dataclass at `agent-coordinator/src/discovery.py` SHALL include a `phase_archetype: str | None = None` field. The agent-status table (or equivalent persistence layer) SHALL include a `phase_archetype TEXT` column. The `DiscoveryService.heartbeat` method SHALL accept an optional `phase_archetype` keyword and SHALL persist it to the matching row.

The schema migration SHALL:
- Be added as a new file under `agent-coordinator/database/migrations/` following the existing migration naming convention.
- Add a single `ALTER TABLE` statement adding `phase_archetype TEXT` to the agent-status table.
- Default to `NULL` for existing rows (no backfill — historical archetypes are unknown).
- Be forward-compatible: existing clients that do not send `phase_archetype` SHALL continue to function.

#### Scenario: AgentInfo round-trip via heartbeat and discovery

- **GIVEN** an autopilot client calls `DiscoveryService.heartbeat(agent_id="a-1", phase_archetype="implementer", ...)`
- **WHEN** a subsequent `GET /discovery/agents` call is made
- **THEN** the response SHALL include the agent record with `phase_archetype: "implementer"`

#### Scenario: AgentInfo without phase_archetype defaults to None

- **GIVEN** an older client calls `DiscoveryService.heartbeat` without `phase_archetype`
- **WHEN** the heartbeat is persisted
- **THEN** the resulting row SHALL have `phase_archetype = NULL`
- **AND** `GET /discovery/agents` SHALL return `phase_archetype: null` for that agent

#### Scenario: Migration applies without backfill

- **GIVEN** the agent-status table contains rows from before the migration
- **WHEN** the new migration is applied
- **THEN** the `phase_archetype` column SHALL be added
- **AND** all existing rows SHALL have `phase_archetype = NULL`
- **AND** the migration SHALL complete without modifying any existing column data
