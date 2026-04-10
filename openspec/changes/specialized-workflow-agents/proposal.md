# Proposal: Specialized Workflow Agents

## Change ID
`specialized-workflow-agents`

## Status
Approved

## Why

Every `Task()` call in our skills runs on Opus — regardless of whether the task is
a five-line lint check or a multi-file architecture decision. This wastes significant
spend on tasks that Sonnet or Haiku handle equally well, and misses an opportunity to
give each workflow stage role-specific instructions that improve output quality.

The Claude Code `Agent` tool already accepts a `model` parameter (`"sonnet"`, `"opus"`,
`"haiku"`), but our skills never use it. The review dispatcher in
`parallel-infrastructure` already has a model fallback chain, but it's vendor-scoped
rather than task-scoped.

This proposal introduces **agent archetypes** — named bundles of model preference,
system prompt, and complexity escalation rules — that map to workflow stages. Skills
reference archetypes instead of raw model strings, and the coordinator routes work to
agents matching the archetype's requirements.

## What Changes

### Phase 1: Static Model Hints in Skills
- Add `model` parameter to `Task()` calls in all skill SKILL.md files
- Map workflow stages to default models (Opus for planning/review, Sonnet for
  implementation, Haiku for runners/validation)
- Zero infrastructure changes — uses existing `Agent` tool `model` parameter

### Phase 2: Agent Archetypes Registry
- New `agent-coordinator/archetypes.yaml` defining named archetypes with model
  preference, system prompt prefix, and constraint metadata
- New `ArchetypeConfig` dataclass in `agents_config.py`
- Loader/validator integrated into existing `load_agents_config()` pipeline
- Skills reference archetype names in `Task()` calls; runtime resolves to model + prompt
- Archetypes extend (not replace) the existing `agents.yaml` model fallback chain

### Phase 3: Coordinator Work Queue Routing
- Add `agent_requirements` field to `work_queue.Task` dataclass
- Add `archetype` field to work-packages.yaml schema
- Extend `claim_task()` RPC and `WorkQueueService.claim()` with requirement matching
- Complexity-based escalation: auto-upgrade Sonnet → Opus when package exceeds
  thresholds (>3 write-allow globs, cross-module deps, or `complexity: high` flag)
- Expose archetype metadata via `/work/claim` HTTP endpoint and MCP `get_work` tool

## Approaches Considered

### Approach A: Layered Archetype System (**Recommended**)

A three-layer architecture where archetypes.yaml defines role bundles, skills reference
archetype names, and the coordinator matches work to capable agents.

**How it works:**
1. `archetypes.yaml` defines named archetypes (architect, implementer, reviewer, runner,
   documenter) each with: model preference, model escalation rules, system prompt prefix,
   constraint metadata (max tokens, allowed tools)
2. Skills use `Task(archetype="implementer", ...)` — runtime resolves archetype to model +
   prompt, composing the archetype's system prompt with the task-specific prompt
3. Work-packages.yaml gains an `archetype` field per package; coordinator `claim()` filters
   available tasks by the claiming agent's archetype compatibility
4. Complexity escalation rules in archetypes.yaml define when to auto-upgrade
   (e.g., implementer escalates from sonnet to opus when write_allow scope spans >3 dirs)

**Pros:**
- Centralized config — tune model assignments without editing every skill
- System prompts per archetype improve output quality (focused implementer vs broad architect)
- Complexity escalation prevents quality regressions on hard tasks
- Extends existing fallback chain — archetypes override primary model but reuse vendor fallbacks
- Backward compatible — skills without archetype behave as today

**Cons:**
- Three-phase delivery — full value requires all phases
- New config file to maintain (archetypes.yaml)
- Complexity escalation heuristics need tuning over time

**Effort:** L (3 phases, touches skills + coordinator + schemas)

### Approach B: Skill-Embedded Model Mapping

Each skill defines its own model/prompt mapping inline — no central registry.

**How it works:**
1. Each skill SKILL.md contains a `## Model Mapping` section with a table mapping
   task types to models and prompt prefixes
2. `Task()` calls read from this table at dispatch time
3. No shared config — each skill is self-contained
4. Work-packages.yaml is unmodified

**Pros:**
- Simple — no new files or abstractions
- Each skill fully controls its model selection
- Phase 1 only, immediate delivery

**Cons:**
- Duplicated model config across 15+ skills — changing "implementer uses sonnet" requires
  editing every skill
- No coordinator awareness — work queue can't route by capability
- No complexity escalation — static per-skill, not per-package
- System prompts duplicated across skills

**Effort:** S

### Approach C: Work-Package Driven Selection

Model selection lives entirely in work-packages.yaml — plan authors set model per package.

**How it works:**
1. work-packages.yaml gains `model` and `system_prompt` fields per package
2. `/plan-feature` sets these during planning based on package complexity
3. `/implement-feature` reads model from the package and passes to `Task(model=...)`
4. No archetype abstraction — direct model assignment per package

**Pros:**
- Maximum per-package control — plan author decides
- No new config files
- Visible in planning artifacts

**Cons:**
- Requires plan authors to make model decisions for every package
- No reusable archetype patterns — each plan reinvents model selection
- System prompts embedded in work-packages.yaml bloat the file
- No automatic escalation — entirely manual
- Coordinator routing limited to what's in the package definition

**Effort:** M

### Selected Approach

**Approach A: Layered Archetype System** — selected because centralized archetype
definitions avoid config duplication across skills, complexity-based escalation
addresses quality concerns for hard implementation tasks, and the three-phase delivery
lets us ship Phase 1 (immediate cost savings) while building toward full routing.

User preferences incorporated:
- **All three phases** in scope (not Phase 1 only)
- **Extend existing fallback** chains rather than independent per-archetype fallbacks
- **Model + system prompts** per archetype (not just model selection)
- **Complexity-based escalation** for implementation tasks (not static assignment)
