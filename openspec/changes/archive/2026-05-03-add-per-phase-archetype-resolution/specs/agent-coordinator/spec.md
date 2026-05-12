# Spec Delta — agent-coordinator (per-phase archetype resolution)

## ADDED Requirements

### Requirement: Phase Archetype Resolution Endpoint

The coordinator HTTP API SHALL expose `POST /archetypes/resolve_for_phase` for resolving an archetype's model and system prompt given a phase name and signal dict.

The endpoint:
- SHALL be served by `agent-coordinator/src/coordination_api.py`.
- SHALL require `X-API-Key` authentication.
- SHALL delegate to `agents_config.resolve_archetype_for_phase(phase, signals)`.
- SHALL return `200` with a JSON body containing `model`, `system_prompt`, `archetype`, and `reasons[]`.
- SHALL return `404` for unknown phase names.
- SHALL return `400` for malformed request bodies.
- SHALL log every successful resolution to the audit trail with `agent_id`, `phase`, `archetype`, and `model`.

#### Scenario: Resolution endpoint returns archetype for known phase

- **GIVEN** a coordinator started with `archetypes.yaml` containing `phase_mapping.PLAN.archetype = "architect"`
- **AND** a valid API key
- **WHEN** the client sends `POST /archetypes/resolve_for_phase` with body `{"phase": "PLAN", "signals": {}}`
- **THEN** the response status SHALL be `200`
- **AND** the response JSON SHALL contain `archetype: "architect"`, `model: "opus"`, `system_prompt` non-empty, and `reasons` non-empty

#### Scenario: Resolution endpoint logs to audit trail

- **WHEN** a client successfully resolves an archetype for a phase
- **THEN** an entry SHALL be written to the audit trail with `operation = "resolve_archetype_for_phase"`, `agent_id` from the API key, `change_id` (if provided in headers or body), `phase`, `archetype`, and `model` fields

#### Scenario: Resolution endpoint with unknown phase

- **WHEN** the client sends a phase name not present in `phase_mapping`
- **THEN** the response status SHALL be `404`
- **AND** the response body SHALL contain an `error` field identifying the unknown phase

---

### Requirement: LoopState Phase Archetype Field

The `LoopState` schema SHALL include an optional field `phase_archetype: str | None` that records the archetype name resolved for the current phase, and the schema version SHALL be bumped from 2 to 3.

The field:
- SHALL default to `None` for newly-created `LoopState` instances.
- SHALL be set by `phase_agent.py` after a successful archetype resolution.
- SHALL be left as `None` if archetype resolution fails (D9 fallback).
- SHALL be persisted in `loop-state.json` and emitted in `POST /status/report` payloads.
- SHALL load with `phase_archetype = None` for older `loop-state.json` files with `schema_version = 2` (graceful migration).

#### Scenario: New LoopState defaults phase_archetype to None

- **WHEN** a new `LoopState` is constructed
- **THEN** `LoopState.phase_archetype` SHALL be `None`
- **AND** `LoopState.schema_version` SHALL be `3`

#### Scenario: Loading older schema_version=2 snapshot

- **GIVEN** a `loop-state.json` file with `schema_version: 2` and no `phase_archetype` field
- **WHEN** `LoopState.from_json(json_str)` is called
- **THEN** the returned `LoopState` SHALL have `phase_archetype = None`
- **AND** no error SHALL be raised
- **AND** `LoopState.schema_version` SHALL be updated to `3` upon next save

#### Scenario: phase_archetype emitted in status report

- **GIVEN** a `LoopState` with `phase = "PLAN"` and `phase_archetype = "architect"`
- **WHEN** the autopilot driver sends `POST /status/report`
- **THEN** the request body SHALL contain `phase_archetype: "architect"` alongside `phase: "PLAN"`

---

### Requirement: Status Report Payload Phase Archetype Field

The `POST /status/report` endpoint SHALL accept and persist a `phase_archetype` field in the request body, alongside the existing `phase` field.

The field:
- SHALL be optional (omitting it SHALL not cause `400` errors — older clients remain compatible).
- SHALL be persisted in the agent-status table or equivalent so observability dashboards can query "which archetype was active in phase X for change Y".
- SHALL be exposed in `GET /status/agents` (or the corresponding listing endpoint) as part of each agent's current-phase summary.

#### Scenario: Status report with phase_archetype is persisted

- **WHEN** an autopilot client sends `POST /status/report` with `{"agent_id": "...", "change_id": "...", "phase": "PLAN", "phase_archetype": "architect"}`
- **THEN** the response status SHALL be `200`
- **AND** subsequent calls to `GET /status/agents` SHALL return `phase_archetype: "architect"` for that agent

#### Scenario: Status report without phase_archetype is accepted

- **WHEN** an older autopilot client sends `POST /status/report` without `phase_archetype`
- **THEN** the response status SHALL be `200`
- **AND** the persisted record SHALL have `phase_archetype = NULL`

---

### Requirement: Phase Archetype Resolution Bridge Helper

The `coordination_bridge` skill SHALL expose a helper function `try_resolve_archetype_for_phase(phase: str, signals: dict[str, Any]) -> dict[str, Any] | None` that wraps the HTTP endpoint with failure tolerance.

The helper:
- SHALL use the existing `coordination_bridge` HTTP client and authentication.
- SHALL return the response body dict (`{model, system_prompt, archetype, reasons}`) on `200`.
- SHALL return `None` on any failure: network error, timeout, non-200 status, malformed JSON response.
- SHALL log each failure as a structured warning including the phase name and the error reason.
- SHALL NOT raise exceptions to the caller (consistent with the `try_*` pattern in the bridge).

#### Scenario: Successful resolution returns dict

- **GIVEN** the coordinator endpoint returns `200` with a valid JSON body
- **WHEN** `try_resolve_archetype_for_phase("PLAN", {})` is called
- **THEN** the function SHALL return a dict containing `model`, `system_prompt`, `archetype`, `reasons`

#### Scenario: HTTP 5xx returns None

- **GIVEN** the coordinator endpoint returns `503`
- **WHEN** `try_resolve_archetype_for_phase("PLAN", {})` is called
- **THEN** the function SHALL return `None`
- **AND** a structured warning SHALL be logged

#### Scenario: Network timeout returns None

- **GIVEN** the HTTP client raises `TimeoutError` when calling the endpoint
- **WHEN** `try_resolve_archetype_for_phase("PLAN", {})` is called
- **THEN** the function SHALL return `None`
- **AND** the caller SHALL NOT see an exception
