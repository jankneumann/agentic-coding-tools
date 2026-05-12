# Spec Delta — agent-archetypes (per-phase archetype resolution)

## ADDED Requirements

### Requirement: Per-Phase Archetype Mapping

The `agent-coordinator/archetypes.yaml` schema SHALL include an optional top-level `phase_mapping` section that maps each non-terminal autopilot phase name to an archetype name plus an optional list of signal keys.

The schema SHALL be:

```yaml
schema_version: 2  # bumped from 1 when phase_mapping is present
archetypes: { ... existing ... }
phase_mapping:
  <PHASE_NAME>:
    archetype: <archetype_name>     # required, must reference a defined archetype
    signals: [<signal_key>, ...]    # optional list of metadata keys to extract for resolve_model
```

The system SHALL define `phase_mapping` entries for all 13 non-terminal autopilot phases: `INIT`, `PLAN`, `PLAN_ITERATE`, `PLAN_REVIEW`, `PLAN_FIX`, `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_REVIEW`, `IMPL_FIX`, `VALIDATE`, `VAL_REVIEW`, `VAL_FIX`, `SUBMIT_PR`.

The system SHALL provide these default mappings:

| Phase | Archetype |
|---|---|
| `PLAN`, `PLAN_ITERATE`, `PLAN_FIX` | `architect` |
| `PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW` | `reviewer` |
| `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_FIX` | `implementer` |
| `VALIDATE`, `VAL_FIX` | `analyst` |
| `INIT`, `SUBMIT_PR` | `runner` |

#### Scenario: Phase mapping is loaded from archetypes.yaml

- **WHEN** `load_archetypes_config(path)` is called on a YAML file containing a `phase_mapping` section
- **THEN** the returned config SHALL expose `phase_mapping` as a `dict[str, PhaseMappingEntry]`
- **AND** each `PhaseMappingEntry` SHALL contain `archetype: str` and `signals: list[str]`
- **AND** the loader SHALL raise `ValueError` if a `phase_mapping` entry references an undefined archetype name

#### Scenario: Older archetypes.yaml without phase_mapping loads successfully

- **GIVEN** an `archetypes.yaml` file with `schema_version: 1` and no `phase_mapping` section
- **WHEN** `load_archetypes_config(path)` is called
- **THEN** the returned config SHALL have `phase_mapping = {}`
- **AND** no warning or error SHALL be emitted

#### Scenario: phase_mapping entry references an undefined archetype

- **GIVEN** an `archetypes.yaml` file with `phase_mapping: { PLAN: { archetype: "nonexistent" } }`
- **WHEN** `load_archetypes_config(path)` is called
- **THEN** the loader SHALL raise `ValueError` with a message identifying the offending phase and archetype name

---

### Requirement: Phase Archetype Resolution Function

The system SHALL expose a function `resolve_archetype_for_phase(phase: str, signals: dict[str, Any]) -> ResolvedArchetype` in `agent-coordinator/src/agents_config.py` that returns the archetype, model, system prompt, and reasons for a given phase plus signal dict.

The function SHALL:
1. Look up the phase in `phase_mapping`. If not found, raise `KeyError`.
2. Resolve the archetype by name.
3. Call `resolve_model(archetype, signals, return_reasons=True, phase=phase)` to get the model and reasons.
4. Return a `ResolvedArchetype` containing `model: str`, `system_prompt: str`, `archetype: str`, `reasons: list[str]`.

The function SHALL ignore signal keys not listed in the phase's `signals` field (silently dropped, not errors).

#### Scenario: Resolve archetype for known phase with empty signals

- **WHEN** `resolve_archetype_for_phase("PLAN", {})` is called
- **THEN** it SHALL return a `ResolvedArchetype` with `archetype="architect"`, `model="opus"`, `system_prompt` set to the architect's system prompt, and `reasons` containing at least `"phase=PLAN maps to archetype=architect"`

#### Scenario: Resolve archetype for unknown phase

- **WHEN** `resolve_archetype_for_phase("UNKNOWN_PHASE", {})` is called
- **THEN** it SHALL raise `KeyError` with a message containing the phase name

#### Scenario: Resolve archetype with escalation-triggering signals

- **GIVEN** the `implementer` archetype has `escalation.loc_threshold: 100`
- **WHEN** `resolve_archetype_for_phase("IMPLEMENT", {"loc_estimate": 250, "write_dirs": ["src/api/**"], "dependencies": []})` is called
- **THEN** the returned `model` SHALL be `"opus"` (escalated)
- **AND** `reasons` SHALL contain a string identifying the loc_estimate as the escalation trigger

---

### Requirement: Phase Archetype Resolution Endpoint Contract

The coordinator SHALL expose an HTTP endpoint `POST /archetypes/resolve_for_phase` that wraps the resolution function and returns the resolved archetype as JSON.

Request schema:
```json
{
  "phase": "<phase_name>",
  "signals": { "<signal_key>": <value>, ... }
}
```

Response schema (200):
```json
{
  "model": "<model_name>",
  "system_prompt": "<archetype system prompt>",
  "archetype": "<archetype_name>",
  "reasons": ["<reason1>", "<reason2>", ...]
}
```

Error responses:
- `400`: malformed body (missing `phase`, non-dict `signals`)
- `401`: missing or invalid `X-API-Key`
- `404`: phase not found in `phase_mapping`
- `500`: archetype configuration error (e.g., invalid YAML, missing archetype)

The endpoint SHALL require `X-API-Key` authentication (consistent with other write endpoints, even though this is read-only — to align with `coordination_bridge` patterns and audit trails).

#### Scenario: Successful phase resolution

- **GIVEN** a valid API key and a coordinator with `phase_mapping.PLAN.archetype = "architect"`
- **WHEN** the client sends `POST /archetypes/resolve_for_phase {"phase": "PLAN", "signals": {}}`
- **THEN** the response status SHALL be `200`
- **AND** the response body SHALL contain `model`, `system_prompt`, `archetype`, and `reasons` fields

#### Scenario: Unknown phase returns 404

- **WHEN** the client sends `POST /archetypes/resolve_for_phase {"phase": "BOGUS", "signals": {}}`
- **THEN** the response status SHALL be `404`
- **AND** the response body SHALL contain an error message identifying the unknown phase

#### Scenario: Missing API key returns 401

- **WHEN** the client sends `POST /archetypes/resolve_for_phase` without an `X-API-Key` header
- **THEN** the response status SHALL be `401`
