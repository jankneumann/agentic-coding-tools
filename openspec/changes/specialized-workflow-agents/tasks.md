# Tasks: Specialized Workflow Agents

## Phase 1: Static Model Hints in Skills

### 1.0 Tests — Phase 1 model hint validation

- [ ] 1.0.1 Write tests for skill Task() model parameter validation
  **Spec scenarios**: agent-archetypes.3 (skill model hint integration)
  **Contracts**: N/A (skill markdown, not API)
  **Design decisions**: D3 (escalation at dispatch time)
  **Dependencies**: None
  Verify that updated skill SKILL.md files include valid `model=` parameters
  on all Task() calls. Write a pytest script that parses SKILL.md files and
  asserts every `Task(` call includes a `model=` parameter.

### 1.1 Add model hints to plan-feature Task() calls

- [ ] 1.1.1 Update plan-feature/SKILL.md — add `model="sonnet"` to all 5 Explore Task() calls in Step 2
  **Dependencies**: 1.0.1
  Files: `skills/plan-feature/SKILL.md`

### 1.2 Add model hints to implement-feature Task() calls

- [ ] 1.2.1 Update implement-feature/SKILL.md — add `model="sonnet"` to general-purpose Task() calls (sequential and local-parallel implementation dispatch)
  **Dependencies**: 1.0.1
  Files: `skills/implement-feature/SKILL.md`

- [ ] 1.2.2 Update implement-feature/SKILL.md — add `model="haiku"` to all 5 Bash Task() calls (pytest, mypy, ruff, openspec validate, validate_flows)
  **Dependencies**: 1.0.1
  Files: `skills/implement-feature/SKILL.md`

### 1.3 Add model hints to iterate-on-plan Task() calls

- [ ] 1.3.1 Update iterate-on-plan/SKILL.md — add `model="sonnet"` to all 5 Explore Task() calls (quality dimension analysis)
  **Dependencies**: 1.0.1
  Files: `skills/iterate-on-plan/SKILL.md`

### 1.4 Add model hints to iterate-on-implementation Task() calls

- [ ] 1.4.1 Update iterate-on-implementation/SKILL.md — add `model="sonnet"` to general-purpose Task() call (finding fixes)
  **Dependencies**: 1.0.1
  Files: `skills/iterate-on-implementation/SKILL.md`

- [ ] 1.4.2 Update iterate-on-implementation/SKILL.md — add `model="haiku"` to all 4 Bash Task() calls (quality checks)
  **Dependencies**: 1.0.1
  Files: `skills/iterate-on-implementation/SKILL.md`

### 1.5 Add model hints to fix-scrub Task() calls

- [ ] 1.5.1 Update fix-scrub/SKILL.md — add `model="sonnet"` to general-purpose Task() call (agent-assisted fixes)
  **Dependencies**: 1.0.1
  Files: `skills/fix-scrub/SKILL.md`

---

## Phase 2: Agent Archetypes Registry

### 2.0 Tests — Archetype configuration loading and validation

- [ ] 2.0.1 Write tests for ArchetypeConfig dataclass and YAML loader
  **Spec scenarios**: agent-archetypes.1 (archetype definition schema — valid load, invalid rejected, unknown fallback)
  **Contracts**: contracts/archetypes-config.schema.json
  **Design decisions**: D1 (configuration not code), D5 (graceful degradation)
  **Dependencies**: None
  Test valid loading, missing required fields, unknown archetype references,
  and graceful fallback behavior.

- [ ] 2.0.2 Write tests for system prompt composition
  **Spec scenarios**: agent-archetypes.2 (predefined archetypes — architect uses opus, runner uses haiku)
  **Contracts**: N/A
  **Design decisions**: D2 (composition not replacement)
  **Dependencies**: None
  Test that archetype system_prompt is prepended to task prompt with separator.

- [ ] 2.0.3 Write tests for complexity-based escalation logic
  **Spec scenarios**: agent-archetypes.4 (complexity-based escalation — large scope, simple package, explicit flag)
  **Contracts**: N/A
  **Design decisions**: D3 (escalation at dispatch time)
  **Dependencies**: None
  Test all four escalation triggers: write_allow dirs, dependencies, loc_estimate, complexity flag.

### 2.1 Create archetypes.yaml with predefined archetypes

- [ ] 2.1.1 Create `agent-coordinator/archetypes.yaml` with 6 predefined archetypes (architect, analyst, implementer, reviewer, runner, documenter)
  **Dependencies**: 2.0.1
  Files: `agent-coordinator/archetypes.yaml`
  Follow the schema defined in design.md. Each archetype includes model, system_prompt, and escalation config.

### 2.2 Add ArchetypeConfig dataclass and loader to agents_config.py

- [ ] 2.2.1 Add `EscalationConfig` and `ArchetypeConfig` dataclasses to `agents_config.py`
  **Dependencies**: 2.0.1
  Files: `agent-coordinator/src/agents_config.py`
  Fields: name, model, system_prompt, escalation (optional EscalationConfig with escalate_to, max_write_dirs, max_dependencies, loc_threshold).

- [ ] 2.2.2 Add `ARCHETYPES_SCHEMA` JSON Schema and `load_archetypes_config()` function
  **Dependencies**: 2.2.1
  Files: `agent-coordinator/src/agents_config.py`
  Follow the `load_agents_config()` pattern: load YAML, validate against schema, return dict of ArchetypeConfig.

- [ ] 2.2.3 Add `resolve_model()` function implementing complexity-based escalation
  **Dependencies**: 2.2.1, 2.0.3
  Files: `agent-coordinator/src/agents_config.py`
  Implement the escalation algorithm from design.md. Accept ArchetypeConfig + package metadata, return resolved model string.

### 2.3 Create archetypes JSON Schema for validation

- [ ] 2.3.1 Create `openspec/schemas/archetypes.schema.json`
  **Dependencies**: 2.0.1
  Files: `openspec/schemas/archetypes.schema.json`
  Define schema for archetypes.yaml with required fields: schema_version, archetypes (map of name to archetype object with model, system_prompt, optional escalation).

### 2.4 Update skills to use archetype parameter

- [ ] 2.4.1 Update all skill SKILL.md files to use `archetype=` instead of `model=` in Task() calls
  **Dependencies**: 2.2.2, 2.1.1
  Files: `skills/plan-feature/SKILL.md`, `skills/implement-feature/SKILL.md`, `skills/iterate-on-plan/SKILL.md`, `skills/iterate-on-implementation/SKILL.md`, `skills/fix-scrub/SKILL.md`
  Replace Phase 1 `model="sonnet"` with `archetype="analyst"` / `archetype="implementer"` etc. per the mapping table in the spec.

---

## Phase 3: Coordinator Work Queue Routing

### 3.0 Tests — Work queue archetype routing

- [ ] 3.0.1 Write tests for work queue agent_requirements filtering
  **Spec scenarios**: agent-archetypes.6 (work queue archetype routing — matched, skipped, backward compatible)
  **Contracts**: contracts/work-queue-requirements.schema.json
  **Design decisions**: D3 (dispatch-time escalation)
  **Dependencies**: None
  Test: task with archetype requirement matched by capable agent, skipped by
  incompatible agent, and claimable by any agent when no requirements.

- [ ] 3.0.2 Write tests for work-packages.yaml archetype field
  **Spec scenarios**: agent-archetypes.7 (work package archetype field — explicit, default)
  **Contracts**: N/A (schema validation)
  **Dependencies**: None
  Test that packages with and without archetype field validate correctly.

### 3.1 Add agent_requirements to work queue Task dataclass

- [ ] 3.1.1 Add `agent_requirements` field to `work_queue.Task` dataclass
  **Dependencies**: 3.0.1
  Files: `agent-coordinator/src/work_queue.py`
  Add optional `agent_requirements: dict[str, Any] | None = None` field with archetype and min_trust_level subfields.

- [ ] 3.1.2 Update `submit()` to accept and persist `agent_requirements`
  **Dependencies**: 3.1.1
  Files: `agent-coordinator/src/work_queue.py`
  Pass agent_requirements through to the submit_task RPC via input_data or a new column.

- [ ] 3.1.3 Update `claim()` to filter by agent_requirements
  **Dependencies**: 3.1.1
  Files: `agent-coordinator/src/work_queue.py`
  When claiming, pass agent's archetype capabilities to claim_task RPC. If task has agent_requirements.archetype, only match agents declaring that archetype.

### 3.2 Add archetype field to work-packages.yaml schema

- [ ] 3.2.1 Add optional `archetype` field to package definition in `work-packages.schema.json`
  **Dependencies**: 3.0.2
  Files: `openspec/schemas/work-packages.schema.json`
  Add `"archetype": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,31}$"}` to package properties.

### 3.3 Expose archetype in coordination API and MCP

- [ ] 3.3.1 Update `coordination_mcp.py` — add `agent_requirements` parameter to `submit_work` tool and archetype filtering to `get_work` tool
  **Dependencies**: 3.1.2, 3.1.3
  Files: `agent-coordinator/src/coordination_mcp.py`

- [ ] 3.3.2 Update `coordination_api.py` — add `agent_requirements` to `/work/submit` endpoint and archetype filtering to `/work/claim` endpoint
  **Dependencies**: 3.1.2, 3.1.3
  Files: `agent-coordinator/src/coordination_api.py`

### 3.4 Update fallback integration in review dispatcher

- [ ] 3.4.1 Update `review_dispatcher.py` to use archetype model as primary instead of agent default
  **Dependencies**: 2.2.2
  Files: `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  **Design decisions**: D4 (extend existing fallback)
  Modify `CliVendorAdapter.dispatch()` to accept optional archetype model override. Build `models_to_try = [archetype_model or cli_config.model] + cli_config.model_fallbacks`.

### 3.5 Database migration for agent_requirements

- [ ] 3.5.1 Create Supabase migration adding `agent_requirements` JSONB column to `work_queue` table
  **Dependencies**: 3.1.1
  Files: `agent-coordinator/supabase/migrations/YYYYMMDD_add_agent_requirements.sql`
  Add nullable JSONB column. Update `claim_task` RPC to filter by archetype when present.
