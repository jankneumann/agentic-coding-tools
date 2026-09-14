## MODIFIED Requirements

### Requirement: Skill Model Hint Integration

All skills that document `Task()` (or equivalent harness dispatch such as
`Agent(...)` / vendor CLI) for model selection SHALL author **archetype or
tier** vocabulary from `archetypes.yaml` (and `phase_mapping`), not raw
harness model names or versions as policy.

At dispatch time, skills SHALL resolve to a harness-specific model id via
`try_resolve_archetype_for_phase` (or an equivalent tier-map resolution) and
pass `model=<resolved_variable>` into the harness, **or** omit `model=` /
CLI model flags when resolution fails. Skills SHALL NOT pass unresolved
archetype names into harness APIs that only accept model ids.

The mapping from workflow stage to archetype SHALL remain:

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

Phase 1 string literals such as `model="sonnet"` or `model="haiku"` SHALL NOT
be treated as a valid end state for skill-authored policy.

#### Scenario: Plan-feature uses analyst for exploration

- **WHEN** `/plan-feature` dispatches parallel Explore tasks in Step 2
- **THEN** the skill SHALL resolve the analyst archetype (or mapped tier) before dispatch
- **AND** each Task() call SHALL use `model=<resolved_variable>` when resolution succeeds
- **AND** the skill SHALL omit `model=` when resolution fails
- **AND** the skill SHALL NOT hardcode a raw model id string (including `model="sonnet"`) as the selection policy

#### Scenario: Implement-feature uses runner for quality checks

- **WHEN** `/implement-feature` dispatches quality check tasks in Step 6
- **THEN** the skill SHALL resolve the runner archetype (or mapped tier) before dispatch
- **AND** each Task() call SHALL use `model=<resolved_variable>` when resolution succeeds
- **AND** the skill SHALL omit `model=` when resolution fails
- **AND** the skill SHALL NOT hardcode `model="haiku"` (or any raw model version) as policy

#### Scenario: Skill Task() call missing model or archetype parameter

- **WHEN** a target lifecycle skill SKILL.md contains a fenced `Task(` dispatch example without a `model=` parameter and without an omit-on-failure instruction for that call
- **THEN** the validation test SHALL fail
- **AND** the test output SHALL identify the skill file and line number

#### Scenario: String-literal model pins are rejected

- **WHEN** a skill SKILL.md fenced dispatch example contains `model="…"` with a string literal, or a vendor CLI `-m <literal-model-id>`
- **THEN** the validation test SHALL fail
- **AND** `model=<variable_name>` forms SHALL remain valid
