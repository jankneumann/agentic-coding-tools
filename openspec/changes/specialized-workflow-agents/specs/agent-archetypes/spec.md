# agent-archetypes Specification

## Purpose

Define agent archetypes — named bundles of model preference, system prompt, and
complexity escalation rules — that enable workflow-stage-aware model selection
across skills and coordinator work routing.

---

## ADDED Requirements

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
- The work-package `loc_estimate` exceeds 500 lines

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

**WHEN** a work-package declares `depends_on: ["wp-a", "wp-b"]` (2+ dependencies)
**AND** the `implementer` archetype has escalation enabled
**THEN** the model SHALL escalate from `sonnet` to `opus`
**AND** the escalation reason SHALL be logged as "depends on >2 packages"

#### Scenario: High LOC estimate triggers escalation

**WHEN** a work-package has `loc_estimate: 600` (exceeds 500 threshold)
**AND** the `implementer` archetype has escalation enabled
**THEN** the model SHALL escalate from `sonnet` to `opus`
**AND** the escalation reason SHALL be logged as "loc_estimate >500"

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
