# agent-archetypes Specification (delta)

## MODIFIED Requirements

### Requirement: Phase Archetype Resolution Function

The system SHALL expose a function `resolve_archetype_for_phase(phase: str, signals: dict[str, Any], *, provider: str | None = None) -> ResolvedArchetype` in `agent-coordinator/src/agents_config.py` that returns the archetype, model, thinking, system prompt, and reasons for a given phase plus signal dict.

The function SHALL:
1. Look up the phase in `phase_mapping`. If not found, raise `KeyError`.
2. Resolve the archetype by name.
3. Call `resolve_model(archetype, signals, return_reasons=True, phase=phase)` to get the model tier and reasons.
4. When `provider` is given, map the tier to the provider's `{model, thinking}` entry from `model_aliases`; when `provider` is `None`, return the tier name in `model` and `thinking = None`, and append the reason `"provider unspecified: model is a tier name, not a dispatchable identifier"`.
5. Return a `ResolvedArchetype` containing `model: str`, `thinking: str | None`, `tier: str`, `system_prompt: str`, `archetype: str`, `reasons: list[str]`, `provider: str | None`, `write_capable: bool`.

The function SHALL ignore signal keys not listed in the phase's `signals` field (silently dropped, not errors).

#### Scenario: Resolve archetype for known phase with empty signals

- **WHEN** `resolve_archetype_for_phase("PLAN", {}, provider="claude_code")` is called
- **THEN** it SHALL return a `ResolvedArchetype` with `archetype="architect"`, `tier="frontier"`, `model` equal to the `claude_code.frontier` alias, `system_prompt` set to the architect's system prompt, and `reasons` containing at least `"phase=PLAN maps to archetype=architect"`

#### Scenario: Provider omitted flags tier-name model

- **WHEN** `resolve_archetype_for_phase("PLAN", {})` is called without a provider
- **THEN** `model` SHALL be `"frontier"`, `thinking` SHALL be `None`
- **AND** `reasons` SHALL contain the string `"provider unspecified"`

#### Scenario: Resolve archetype for unknown phase

- **WHEN** `resolve_archetype_for_phase("UNKNOWN_PHASE", {})` is called
- **THEN** it SHALL raise `KeyError` with a message containing the phase name

#### Scenario: Resolve archetype with escalation-triggering signals

- **GIVEN** the `implementer` archetype has `escalation.loc_threshold: 100`
- **WHEN** `resolve_archetype_for_phase("IMPLEMENT", {"loc_estimate": 250, "write_dirs": ["src/api/**"], "dependencies": []}, provider="codex")` is called
- **THEN** the returned `tier` SHALL be `"premium"` (escalated)
- **AND** `thinking` SHALL equal the `codex.premium.thinking` value
- **AND** `reasons` SHALL contain a string identifying the loc_estimate as the escalation trigger

### Requirement: Phase Archetype Resolution Endpoint Contract

The coordinator SHALL expose an HTTP endpoint `POST /archetypes/resolve_for_phase` that wraps the resolution function and returns the resolved archetype as JSON.

Request schema:
```json
{
  "phase": "<phase_name>",
  "signals": { "<signal_key>": <value>, ... },
  "provider": "<provider_name or null>"
}
```

Response schema (200):
```json
{
  "model": "<model_name>",
  "thinking": "<thinking_level or null>",
  "tier": "<tier_name>",
  "system_prompt": "<archetype system prompt>",
  "archetype": "<archetype_name>",
  "reasons": ["<reason1>", "<reason2>", ...],
  "provider": "<provider_name or null>",
  "write_capable": true
}
```

Error responses:
- `400`: malformed body (missing `phase`, non-dict `signals`)
- `401`: missing or invalid `X-API-Key`
- `404`: phase not found in `phase_mapping`
- `500`: archetype configuration error (e.g., invalid YAML, missing archetype)

The endpoint SHALL require `X-API-Key` authentication (consistent with other write endpoints, even though this is read-only — to align with `coordination_bridge` patterns and audit trails). The audit entry for the resolution SHALL record `thinking` and `tier` alongside `model`.

#### Scenario: Successful phase resolution

- **GIVEN** a valid API key and a coordinator with `phase_mapping.PLAN.archetype = "architect"`
- **WHEN** the client sends `POST /archetypes/resolve_for_phase {"phase": "PLAN", "signals": {}, "provider": "codex"}`
- **THEN** the response status SHALL be `200`
- **AND** the response body SHALL contain `model`, `thinking`, `tier`, `system_prompt`, `archetype`, and `reasons` fields
- **AND** the audit log entry SHALL contain `thinking` in its `result`

#### Scenario: Unknown phase returns 404

- **WHEN** the client sends `POST /archetypes/resolve_for_phase {"phase": "BOGUS", "signals": {}}`
- **THEN** the response status SHALL be `404`
- **AND** the response body SHALL contain an error message identifying the unknown phase

#### Scenario: Missing API key returns 401

- **WHEN** the client sends `POST /archetypes/resolve_for_phase` without an `X-API-Key` header
- **THEN** the response status SHALL be `401`

## ADDED Requirements

### Requirement: Archetype Enum Parity For Status Reporting

Every place that enumerates accepted archetype names outside `archetypes.yaml` — the client-side
allow-list in `agent-coordinator/scripts/report_status.py`, the `/status/report` Pydantic literal,
and the `agent_sessions.phase_archetype` CHECK constraint — SHALL accept every archetype defined in
`archetypes.yaml`, including `validator`, `supervisor`, and `documenter`. A test SHALL assert that
each enumeration equals the set of archetype keys in `archetypes.yaml`, so that adding an archetype
without widening the enumerations fails CI.

#### Scenario: VALIDATE phase archetype persists

- **GIVEN** `phase_mapping.VALIDATE.archetype = "validator"`
- **WHEN** the Stop hook reports status for a VALIDATE phase
- **THEN** `agent_sessions.phase_archetype` SHALL equal `"validator"` for that session
- **AND** the report script SHALL NOT drop the value client-side

#### Scenario: Enum drift fails CI

- **WHEN** a new archetype is added to `archetypes.yaml` without updating the three enumerations
- **THEN** the parity test SHALL fail naming the missing archetype and the stale location
