# Design: Specialized Workflow Agents

## Overview

This design introduces a three-layer archetype system that maps workflow stages to
model selection, system prompts, and complexity escalation rules. The layers are
independent and deliverable as sequential phases.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Skill SKILL.md                                          │
│   Task(archetype="implementer", prompt="...")            │
│         │                                                │
│         ▼                                                │
│ ┌───────────────────┐  ┌────────────────────────┐       │
│ │ archetypes.yaml   │  │ agents.yaml            │       │
│ │ ├─ model: sonnet  │  │ ├─ cli.model_fallbacks │       │
│ │ ├─ system_prompt  │  │ └─ sdk.model_fallbacks │       │
│ │ └─ escalation     │  │                        │       │
│ └────────┬──────────┘  └───────────┬────────────┘       │
│          │                         │                     │
│          ▼                         ▼                     │
│ ┌──────────────────────────────────────────────┐        │
│ │ Resolution: archetype.model + agent.fallbacks │        │
│ │ Escalation: complexity check → model override  │        │
│ └──────────────────────┬───────────────────────┘        │
│                        ▼                                 │
│ ┌──────────────────────────────┐                        │
│ │ Agent tool: model="sonnet"   │                        │
│ │ Prompt: system_prompt + task │                        │
│ └──────────────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

## Design Decisions

### D1: Archetypes are configuration, not code

**Decision**: Archetypes are defined in YAML, not as Python classes.

**Rationale**: Archetypes are tuning parameters (model choice, prompt text, thresholds).
Making them YAML means operators can adjust model assignments, prompt wording, and
escalation thresholds without modifying code. Follows the `agents.yaml` pattern.

**Alternative rejected**: Python enum/dataclass per archetype — adds type safety but
requires code changes to tune model assignments. Not worth the friction for what is
essentially configuration.

### D2: System prompt composition, not replacement

**Decision**: Archetype system prompts are **prepended** to task-specific prompts, not
replacing them.

**Rationale**: Task-specific prompts in skills already contain detailed context (file
scopes, contract references, work-package instructions). The archetype system prompt
adds role framing ("You are a focused implementer...") that shapes behavior without
losing task specifics.

**Format**:
```
[archetype.system_prompt]\n\n---\n\n[task.prompt]
```

**Alternative rejected**: Archetype prompt replaces task prompt — loses critical
per-task context that skills already provide.

### D3: Escalation checks at dispatch time, not claim time

**Decision**: Complexity-based escalation is evaluated when the skill dispatches a
Task(), not when the coordinator assigns it.

**Rationale**: The skill has access to the work-package definition (write_allow scope,
dependency count, complexity flag) at dispatch time. The coordinator's claim() would
need the same information passed through input_data, adding coupling. Dispatch-time
escalation is simpler and works for all tiers including sequential (no coordinator).

**Alternative rejected**: Coordinator-side escalation — requires all complexity signals
in task input_data, only works for coordinated tier, and adds latency to claim().

### D4: Extend existing fallback, don't duplicate

**Decision**: Archetypes override the primary model in the fallback chain but reuse the
agent's existing fallback sequence from `agents.yaml`.

**Rationale**: The review_dispatcher already implements robust fallback logic with retry
on 429s. Duplicating fallback chains per archetype creates maintenance burden and
divergence risk. By overriding only the primary model, archetypes compose cleanly with
the existing infrastructure.

**Implementation**: `CliVendorAdapter.dispatch()` currently builds
`models_to_try = [self.cli_config.model] + self.cli_config.model_fallbacks`.
With archetypes, this becomes
`models_to_try = [archetype.resolved_model] + self.cli_config.model_fallbacks`.

**Resolution callsite**: Skills call `resolve_model(archetype, package_metadata)` and
`compose_prompt(archetype, task_prompt)` at dispatch time, then pass the resolved model
string and composed prompt to the `Agent` tool or `CliVendorAdapter.dispatch()`. The
Agent tool itself does NOT understand archetypes — it receives a concrete `model=` and
`prompt=`. This keeps the resolution layer in the skill dispatch code, not in framework
internals.

### D5: Graceful degradation for unknown archetypes

**Decision**: If a skill references an archetype that doesn't exist in
`archetypes.yaml`, fall back to the ambient model with a warning log.

**Rationale**: Hard failure would break skills if `archetypes.yaml` is deleted or
renamed. Graceful degradation preserves backward compatibility — the system works
exactly as it does today (all Opus), just without the optimization.

### D6: Single archetypes.yaml file adjacent to agents.yaml

**Decision**: Place `archetypes.yaml` in `agent-coordinator/` alongside `agents.yaml`.

**Rationale**: Both files configure agent behavior. Co-location makes them discoverable
together. The loader in `agents_config.py` already handles YAML loading, validation,
and secret interpolation — extending it for archetypes is natural.

**Alternative rejected**: Per-skill archetype config — duplicates model assignments,
requires editing 8+ skill files to change a model, violates DRY.

### D7: Orthogonal coexistence with speculative merge trains

**Decision**: Archetype routing and merge train routing are orthogonal filtering
dimensions that compose independently in `claim()`.

**Rationale**: The speculative merge trains feature (landed April 2026) added
`compose_train`, `eject_from_train`, `get_train_status`, `report_spec_result`,
and `affected_tests` MCP tools to `coordination_mcp.py`, plus corresponding HTTP
endpoints in `coordination_api.py`. It also added `decomposition` and
`stack_position` fields to the work-packages schema. These concern *how* packages
are merged (stacked vs. branch, wave ordering), while archetypes concern *who*
executes them (model + prompt + escalation). The two features filter on different
axes: merge trains filter by partition/wave position, archetypes filter by agent
capability.

**Implementation**: `claim()` applies archetype filtering *after* existing
task_type and priority filtering, before merge-train-aware ordering. The
`archetype` field in `work-packages.schema.json` sits alongside `decomposition`
and `stack_position` — all are optional package-level metadata.

**Alternative rejected**: Merging archetype into merge train metadata — conflates
agent selection with merge strategy, creating unnecessary coupling.

## Escalation Algorithm

```python
def resolve_model(archetype: ArchetypeConfig, package: WorkPackage) -> str:
    """Resolve the effective model for a work package."""
    if not archetype.escalation:
        return archetype.model

    rules = archetype.escalation
    reasons = []

    if rules.max_write_dirs and len(unique_dirs(package.write_allow)) > rules.max_write_dirs:
        reasons.append(f"write_allow spans >{rules.max_write_dirs} directories")

    if rules.max_dependencies and len(package.dependencies) > rules.max_dependencies:
        reasons.append(f"depends on >{rules.max_dependencies} packages")

    if rules.loc_threshold and (package.loc_estimate or 0) > rules.loc_threshold:
        reasons.append(f"loc_estimate >{rules.loc_threshold}")

    if getattr(package, 'complexity', None) == 'high':
        reasons.append("explicit complexity: high flag")

    if reasons:
        logger.info(f"Escalating {archetype.name} to {rules.escalate_to}: {', '.join(reasons)}")
        return rules.escalate_to

    return archetype.model
```

## File Layout

```
agent-coordinator/
├── agents.yaml              # Existing — unchanged
├── archetypes.yaml          # NEW — archetype definitions
├── src/
│   ├── agents_config.py     # MODIFIED — add ArchetypeConfig, loader, validator
│   ├── work_queue.py        # MODIFIED — add agent_requirements to Task, claim filtering
│   ├── coordination_mcp.py  # MODIFIED — expose archetype in get_work/submit_work
│   └── coordination_api.py  # MODIFIED — expose archetype in /work/claim, /work/submit

skills/
├── plan-feature/SKILL.md           # MODIFIED — add model/archetype to Task() calls
├── implement-feature/SKILL.md      # MODIFIED — add model/archetype to Task() calls
├── iterate-on-plan/SKILL.md        # MODIFIED — add model/archetype to Task() calls
├── iterate-on-implementation/SKILL.md  # MODIFIED — add model/archetype to Task() calls
├── fix-scrub/SKILL.md              # MODIFIED — add model/archetype to Task() calls

openspec/schemas/
└── work-packages.schema.json       # MODIFIED — add optional archetype field to packages
```

## Archetype Configuration Schema

```yaml
# agent-coordinator/archetypes.yaml
schema_version: 1

archetypes:
  architect:
    model: opus
    system_prompt: |
      You are a software architect. Focus on cross-cutting concerns, dependency
      ordering, interface contracts, and long-term maintainability. Think deeply
      before committing to a design. Identify risks and trade-offs explicitly.
    escalation: null  # Architect always uses opus

  analyst:
    model: sonnet
    system_prompt: |
      You are a codebase analyst. Read thoroughly, synthesize findings concisely,
      and identify patterns, gaps, and conflicts. Report structured findings
      without making changes.
    escalation: null  # Analyst is read-only, no escalation needed

  implementer:
    model: sonnet
    system_prompt: |
      You are a focused implementer. Follow the work-package contract exactly.
      Do not refactor beyond scope. Write tests for new code. Keep changes
      minimal and well-scoped. If you encounter ambiguity, prefer the simpler
      interpretation.
    escalation:
      escalate_to: opus
      max_write_dirs: 3
      max_dependencies: 2
      loc_threshold: 500

  reviewer:
    model: opus
    system_prompt: |
      You are a code reviewer. Evaluate correctness, security, performance, and
      adherence to contracts. Identify issues by severity. Be specific about
      locations and fixes. Do not rewrite code — describe what should change.
    escalation: null  # Reviewer always uses opus

  runner:
    model: haiku
    system_prompt: |
      Execute the requested command and report results. Include exit codes,
      error output, and pass/fail summary. Do not analyze or suggest fixes.
    escalation: null  # Runner always uses haiku

  documenter:
    model: sonnet
    system_prompt: |
      You are a documentation writer. Update specs, changelogs, and architecture
      artifacts to match implementation reality. Be precise and concise. Follow
      existing formatting conventions.
    escalation: null
```

## Migration Path

### Phase 1 (no infrastructure changes)
Skills use `model=` parameter directly:
```python
# Before
Task(subagent_type="Explore", prompt="...", run_in_background=true)

# After (Phase 1)
Task(subagent_type="Explore", model="sonnet", prompt="...", run_in_background=true)
```

### Phase 2 (archetypes.yaml + loader)
Skills resolve archetype to model + composed prompt at dispatch time, then pass
concrete values to the Agent tool. The Agent tool itself does NOT gain an
`archetype=` parameter — resolution happens in skill dispatch code:
```python
# After (Phase 2) — skill SKILL.md dispatch instructions
# 1. Resolve archetype to model
archetype = get_archetype("analyst")
resolved_model = resolve_model(archetype, package_metadata)
composed_prompt = compose_prompt(archetype, task_prompt)

# 2. Dispatch with concrete values
Task(subagent_type="Explore", model=resolved_model, prompt=composed_prompt, run_in_background=true)
```

**Runtime integration**: Skills express this as SKILL.md instructions, not executable
Python. The implementing agent reads the archetype name from the SKILL.md, calls
`load_archetypes_config()` and `resolve_model()` from `agents_config.py`, then
passes the resolved model and composed prompt to the `Task()` call. This avoids
changes to the Claude Code Agent tool internals while still getting archetype-driven
model selection and prompt composition.

### Phase 3 (coordinator routing)
Work-packages carry archetype; coordinator matches agents to tasks:
```yaml
# work-packages.yaml
packages:
  - id: wp-backend
    archetype: implementer
    tasks: [2.1, 2.2]
```
