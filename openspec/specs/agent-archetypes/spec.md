# agent-archetypes Specification

## Purpose
TBD - created by archiving change specialized-workflow-agents. Update Purpose after archive.
## Requirements
### Requirement: Archetype Definition Schema

The system SHALL support an `archetypes.yaml` configuration file that defines
named agent archetypes. Each archetype SHALL specify:
- `model`: Primary model identifier (`opus`, `sonnet`, `haiku`)
- `system_prompt`: Role-specific instruction prefix composed with task prompts
- `escalation`: Optional rules for complexity-based model upgrade
The archetype schema SHALL be validated at load time using JSON Schema, following
the `agents.yaml` validation pattern in `agents_config.py`.

Archetype names SHALL match the pattern `^[a-z][a-z0-9_-]{0,31}$` and SHALL be
validated at all system boundaries (config loading, API submission, MCP tools).

The archetype configuration SHALL be loaded once at startup and cached in a
module-level singleton (following the `_agents` cache pattern in `agents_config.py`).
Subsequent calls to `get_archetype()` SHALL return cached results without file I/O.

#### Scenario: Valid archetype loads successfully

**WHEN** `archetypes.yaml` contains an archetype named `implementer` with
model `sonnet`, a system_prompt string, and escalation rules
**THEN** `load_archetypes_config()` SHALL return an `ArchetypeConfig` with
all fields populated
**AND** the archetype SHALL be accessible by name via `get_archetype("implementer")`

#### Scenario: Invalid archetype rejected at load time

**WHEN** `archetypes.yaml` contains an archetype missing the required `model` field
**THEN** `load_archetypes_config()` SHALL raise a `ValidationError`
**AND** the error message SHALL identify the missing field and archetype name

#### Scenario: Unknown archetype referenced in Task call

**WHEN** a skill references `archetype="nonexistent"` in a Task() call
**THEN** the runtime SHALL fall back to the ambient model (current behavior)
**AND** SHALL log a warning identifying the unknown archetype name

#### Scenario: Archetypes config file not found at runtime

**WHEN** `archetypes.yaml` does not exist at the expected path
**THEN** `load_archetypes_config()` SHALL return an empty dict
**AND** SHALL log a warning identifying the missing file path
**AND** all subsequent `get_archetype()` calls SHALL return `None`

---

### Requirement: Predefined Archetypes

The system SHALL ship with the following predefined archetypes:

| Archetype | Model | Role |
|-----------|-------|------|
| `architect` | opus | Planning, architecture decisions, cross-package dependency analysis |
| `analyst` | sonnet | Codebase exploration, gap analysis, context gathering |
| `implementer` | sonnet | Single work-package implementation, file edits, test writing |
| `reviewer` | opus | Review consensus synthesis, security review, cross-package coherence |
| `runner` | haiku | Linting, test execution, validation gates, schema checks |
| `documenter` | sonnet | Spec sync, changelog, architecture artifact refresh |

Each predefined archetype SHALL include a `system_prompt` tuned to its role.

#### Scenario: Architect archetype uses Opus for planning

**WHEN** a skill dispatches `Task(archetype="architect", ...)`
**THEN** the task SHALL execute with model `opus`
**AND** the system prompt SHALL contain the phrase "software architect"

#### Scenario: Runner archetype uses Haiku for validation

**WHEN** a skill dispatches `Task(archetype="runner", ...)`
**THEN** the task SHALL execute with model `haiku`
**AND** the system prompt SHALL contain the phrase "execute" and "report"

---

### Requirement: Skill Model Hint Integration

All skills that use `Task()` calls SHALL be updated to include either a `model`
parameter (Phase 1) or an `archetype` parameter (Phase 2+) on each Task() call.

The mapping from workflow stage to archetype SHALL be:

| Skill | Task Type | Archetype |
|-------|-----------|-----------|
| plan-feature | Explore context gathering | analyst |
| plan-feature | Proposal drafting (main agent) | architect (informational — main agent is the conversation, not a Task() call) |
| iterate-on-plan | Quality dimension analysis | analyst |
| implement-feature | Work-package implementation | implementer |
| implement-feature | Quality checks (pytest, mypy, ruff) | runner |
| iterate-on-implementation | Finding fixes | implementer |
| iterate-on-implementation | Quality checks | runner |
| fix-scrub | Agent-assisted fixes | implementer |

#### Scenario: Plan-feature uses analyst for exploration

**WHEN** `/plan-feature` dispatches parallel Explore tasks in Step 2
**THEN** each Task() call SHALL include `model="sonnet"` (Phase 1)
or `archetype="analyst"` (Phase 2+)

#### Scenario: Implement-feature uses runner for quality checks

**WHEN** `/implement-feature` dispatches quality check tasks in Step 6
**THEN** each Task() call SHALL include `model="haiku"` (Phase 1)
or `archetype="runner"` (Phase 2+)

#### Scenario: Skill Task() call missing model or archetype parameter

**WHEN** a skill SKILL.md file contains a `Task(` call without a `model=`
parameter (Phase 1) or `archetype=` parameter (Phase 2+)
**THEN** the validation test SHALL fail
**AND** the test output SHALL identify the skill file and line number

---

### Requirement: Complexity-Based Escalation

The `implementer` archetype SHALL support automatic model escalation from
`sonnet` to `opus` based on work-package complexity signals.

Escalation SHALL trigger when ANY of these conditions are met:
- The work-package `write_allow` scope spans more than 3 directory prefixes
- The work-package declares cross-module dependencies (depends on 2+ other packages)
- The work-package includes an explicit `complexity: high` flag
- The work-package `loc_estimate` exceeds the configured `loc_threshold` (default: 100 lines)

When escalation triggers, the runtime SHALL:
1. Log the escalation reason
2. Override the archetype's primary model to `opus`
3. Retain the archetype's system prompt (implementer instructions, not architect)

#### Scenario: Large scope triggers escalation

**WHEN** a work-package has `write_allow: ["src/api/**", "src/models/**", "src/services/**", "tests/**"]`
**AND** the `implementer` archetype has escalation enabled
**THEN** the model SHALL escalate from `sonnet` to `opus`
**AND** the escalation reason SHALL be logged as "write_allow spans >3 directories"

#### Scenario: Simple package stays on Sonnet

**WHEN** a work-package has `write_allow: ["src/api/users.py"]` and no cross-module deps
**THEN** the model SHALL remain `sonnet` (no escalation)

#### Scenario: Cross-module dependencies trigger escalation

**WHEN** a work-package declares `depends_on: ["wp-a", "wp-b", "wp-c"]` (3 dependencies, exceeding the threshold of 2)
**AND** the `implementer` archetype has escalation enabled
**THEN** the model SHALL escalate from `sonnet` to `opus`
**AND** the escalation reason SHALL be logged as "depends on >2 packages"

#### Scenario: High LOC estimate triggers escalation

**WHEN** a work-package has `loc_estimate: 150` (exceeds 100 threshold)
**AND** the `implementer` archetype has escalation enabled
**THEN** the model SHALL escalate from `sonnet` to `opus`
**AND** the escalation reason SHALL be logged as "loc_estimate >100"

#### Scenario: Explicit complexity flag triggers escalation

**WHEN** a work-package includes `complexity: high` in its metadata
**THEN** the model SHALL escalate to `opus` regardless of scope size

---

### Requirement: Fallback Chain Integration

Archetype model selection SHALL integrate with the existing `agents.yaml`
model fallback chain rather than defining independent fallback sequences.

The resolution order SHALL be:
1. Archetype primary model (potentially escalated)
2. `agents.yaml` `cli.model_fallbacks` for the active agent
3. `agents.yaml` `sdk.model` and `sdk.model_fallbacks` (if SDK dispatch available)

#### Scenario: Archetype model exhausted falls back to agents.yaml chain

**WHEN** the `reviewer` archetype specifies model `opus`
**AND** the primary model dispatch returns an `ErrorClass.CAPACITY` error
(testable via `respx` mock returning HTTP 429)
**THEN** the dispatcher SHALL try the next model in the agent's
`cli.model_fallbacks` list (e.g., `claude-sonnet-4-6`)
**AND** SHALL NOT define its own independent fallback chain

#### Scenario: All models in fallback chain exhausted

**WHEN** the `implementer` archetype specifies model `sonnet`
**AND** both the primary model and all `cli.model_fallbacks` return errors
**THEN** the dispatcher SHALL raise a dispatch failure with the last error
**AND** SHALL NOT retry models already attempted in this dispatch

---

### Requirement: Work Queue Archetype Routing

The coordinator work queue SHALL support archetype-aware task routing.

The `submit_work()` operation SHALL accept an optional `agent_requirements`
parameter containing:
- `archetype`: Preferred archetype name
- `min_trust_level`: Minimum trust level required (optional)

The `claim_task()` operation SHALL filter available tasks by the claiming
agent's declared archetype compatibility when `agent_requirements` is present.

#### Scenario: Task with archetype requirement matched to capable agent

**WHEN** a task is submitted with `agent_requirements.archetype = "reviewer"`
**AND** an agent with `archetypes: ["reviewer", "architect"]` calls `claim()`
**THEN** the agent SHALL successfully claim the task

#### Scenario: Task with archetype requirement skipped by incompatible agent

**WHEN** a task is submitted with `agent_requirements.archetype = "reviewer"`
**AND** an agent with `archetypes: ["runner"]` calls `claim()`
**THEN** the task SHALL NOT be claimed by this agent
**AND** the claim result SHALL indicate no matching tasks available

#### Scenario: Task without archetype requirement claimable by any agent

**WHEN** a task is submitted without `agent_requirements`
**THEN** any agent SHALL be able to claim it (backward compatible)

---

### Requirement: Work Package Archetype Field

The `work-packages.yaml` schema SHALL support an optional `archetype` field
per package, allowing plan authors to specify the intended agent archetype.

The field SHALL be optional with no default — packages without an archetype
field SHALL use the skill's default mapping.

#### Scenario: Package with explicit archetype

**WHEN** a work-package specifies `archetype: "architect"`
**THEN** `/implement-feature` SHALL dispatch the package with the
`architect` archetype instead of the default `implementer`

#### Scenario: Package without archetype uses skill default

**WHEN** a work-package omits the `archetype` field
**THEN** `/implement-feature` SHALL use the `implementer` archetype
as the default for implementation packages

#### Scenario: Package with invalid archetype name rejected

**WHEN** a work-package specifies `archetype: "INVALID_NAME"`
**THEN** `openspec validate` SHALL reject the work-packages.yaml file
**AND** the error message SHALL identify the invalid archetype name and the
validation pattern `^[a-z][a-z0-9_-]{0,31}$`

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

